#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND_TIMEOUT = 300.0
MIN_COMMAND_TIMEOUT = 0.05
MAX_COMMAND_TIMEOUT = 3600.0


def run(command, env, timeout=None):
    print("+", " ".join(command), flush=True)
    result = _capture(command, env, timeout=timeout)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    return result.returncode


def worker_count(env):
    raw = env.get("CLONAMIC_TEST_WORKERS", str(min(8, os.cpu_count() or 1)))
    try:
        workers = int(raw)
    except ValueError as error:
        raise ValueError("CLONAMIC_TEST_WORKERS must be an integer from 1 to 8") from error
    if not 1 <= workers <= 8:
        raise ValueError("CLONAMIC_TEST_WORKERS must be from 1 to 8")
    return workers


def command_timeout(env):
    raw = env.get("CLONAMIC_TEST_TIMEOUT_SECONDS", str(DEFAULT_COMMAND_TIMEOUT))
    try:
        timeout = float(raw)
    except ValueError as error:
        raise ValueError(
            "CLONAMIC_TEST_TIMEOUT_SECONDS must be a number from 0.05 to 3600"
        ) from error
    if not MIN_COMMAND_TIMEOUT <= timeout <= MAX_COMMAND_TIMEOUT:
        raise ValueError(
            "CLONAMIC_TEST_TIMEOUT_SECONDS must be from 0.05 to 3600"
        )
    return timeout


def test_binary_path(env):
    target = Path(env.get("CARGO_TARGET_DIR", "target"))
    if not target.is_absolute():
        target = ROOT / target
    return target / "debug" / ("clonamic.exe" if os.name == "nt" else "clonamic")


def build_plan():
    package_commands = [
        [sys.executable, "-m", "unittest", f"tests.{path.stem}", "-v"]
        for path in sorted((ROOT / "tests").glob("test_*.py"))
    ]
    for package_tests in sorted(ROOT.glob("plugins/*/tests")):
        if any(package_tests.glob("test*.py")):
            package_commands.append(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(package_tests.relative_to(ROOT)),
                    "-v",
                ]
            )
    package_commands.append(
        [sys.executable, "plugins/clonamic-ppt/skills/clonamic-ppt/tests/run_all.py"]
    )
    package_commands.append(["cargo", "fmt", "--check"])
    return {
        "before": [
            [sys.executable, "io.github.algocean1204.clonamic/adapters/generate.py", "--check"],
            ["cargo", "build", "--quiet", "--bin", "clonamic"],
        ],
        "packages": package_commands,
        "after": [
            ["cargo", "clippy", "--all-targets", "--", "-D", "warnings"],
            ["cargo", "test", "--all-targets"],
        ],
    }


def _windows_job(process):
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    return job


def _cleanup_process_tree(process, job=None):
    if os.name == "nt":
        if job:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(job)
        elif process.poll() is None:
            process.terminate()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    time.sleep(0.05)
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


def _capture(command, env, cancel=None, timeout=None):
    cancel = cancel or threading.Event()
    options = {
        "cwd": ROOT,
        "env": env,
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    job = None
    try:
        job = _windows_job(process) if os.name == "nt" else None
    except BaseException:
        _cleanup_process_tree(process)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=1)
        raise
    interrupted = False
    expired = False
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        while True:
            if cancel.is_set():
                interrupted = True
                break
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                expired = True
                break
            try:
                stdout, stderr = process.communicate(
                    timeout=0.05 if remaining is None else min(0.05, remaining)
                )
                break
            except subprocess.TimeoutExpired:
                if process.poll() is not None:
                    _cleanup_process_tree(process, job)
                    job = None
                    stdout, stderr = process.communicate()
                    break
        returncode = process.returncode
        if interrupted or expired:
            _cleanup_process_tree(process, job)
            job = None
            stdout, stderr = process.communicate()
            if interrupted:
                returncode = 130
            else:
                returncode = 124
                message = f"command timed out after {timeout:g} seconds"
                separator = "" if not stderr or stderr.endswith("\n") else "\n"
                stderr = f"{stderr}{separator}{message}\n"
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)
    finally:
        _cleanup_process_tree(process, job)


def run_parallel(commands, env, workers, stream=sys.stdout, timeout=None):
    cancel = threading.Event()
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = [
        executor.submit(_capture, command, env, cancel, timeout) for command in commands
    ]
    try:
        results = [future.result() for future in futures]
    except BaseException:
        cancel.set()
        for future in futures:
            with suppress(BaseException):
                future.result()
        raise
    finally:
        executor.shutdown(wait=True)
    status = 0
    for command, result in zip(commands, results):
        print("+", " ".join(command), file=stream)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", file=stream)
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=stream)
        if status == 0 and result.returncode != 0:
            status = result.returncode
    stream.flush()
    return status


def main():
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    env["CLONAMIC_OFFLINE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        workers = worker_count(env)
        timeout = command_timeout(env)
    except ValueError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    plan = build_plan()
    for command in plan["before"]:
        status = run(command, env, timeout)
        if status != 0:
            return status
    env["CLONAMIC_TEST_BINARY"] = str(test_binary_path(env))
    env["CLONAMIC_ROOT_SUITE_ACTIVE"] = "1"
    status = run_parallel(plan["packages"], env, workers, timeout=timeout)
    if status != 0:
        return status
    for command in plan["after"]:
        status = run(command, env, timeout)
        if status != 0:
            return status
    count = sum(len(commands) for commands in plan.values())
    print(f"validation passed: {count} local commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
