from __future__ import annotations

import importlib.util
import io
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_public", ROOT / "scripts" / "validate-public.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


def detached_child_command(pid_file, exit_code=0, linger=False):
    child = "import time; time.sleep(30)"
    script = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-c',{child!r}],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); "
        + ("time.sleep(30); " if linger else "")
        + f"sys.exit({exit_code})"
    )
    return [sys.executable, "-c", script]


def pid_exists(pid):
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for_file(path, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def assert_process_exits(test, pid, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and pid_exists(pid):
        time.sleep(0.02)
    test.assertFalse(pid_exists(pid), f"detached child {pid} survived")


class ValidationRunnerTest(unittest.TestCase):
    def test_plan_keeps_only_independent_package_tests_parallel(self):
        plan = VALIDATOR.build_plan()
        self.assertEqual("scripts/generate-adapters.py", plan["before"][0][1])
        self.assertEqual(1, len(plan["before"]))
        self.assertEqual("tests", plan["packages"][0][-2])
        self.assertEqual(
            sorted(
                str(path.relative_to(ROOT))
                for path in ROOT.glob("plugins/*/tests")
                if any(path.glob("test*.py"))
            ),
            [command[-2] for command in plan["packages"][1:]],
        )
        self.assertEqual(
            "plugins/clonamic-ppt/skills/clonamic-ppt/tests/run_all.py",
            plan["after"][0][1],
        )
        self.assertEqual(
            ["fmt", "check", "clippy", "test"],
            [command[1] for command in plan["after"][1:]],
        )

    def test_worker_override_accepts_only_one_through_four(self):
        for value in range(1, 5):
            with self.subTest(value=value):
                self.assertEqual(
                    value, VALIDATOR.worker_count({"CLONAMIC_TEST_WORKERS": str(value)})
                )
        self.assertEqual(4, VALIDATOR.worker_count({}))
        for value in ("0", "5", "many"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VALIDATOR.worker_count({"CLONAMIC_TEST_WORKERS": value})

    def test_parallel_packages_reduce_wall_time(self):
        commands = [
            [sys.executable, "-c", "import time; time.sleep(0.5)"]
            for _ in range(3)
        ]
        started = time.monotonic()
        status = VALIDATOR.run_parallel(
            commands, os.environ.copy(), workers=3, stream=io.StringIO()
        )
        elapsed = time.monotonic() - started
        self.assertEqual(0, status)
        self.assertLess(elapsed, 1.2, f"parallel package tests took {elapsed:.3f}s")

    def test_parallel_output_and_failure_status_follow_plan_order(self):
        commands = [
            [
                sys.executable,
                "-c",
                "import sys,time; time.sleep(0.20); print('first-result'); sys.exit(7)",
            ],
            [
                sys.executable,
                "-c",
                "import sys,time; time.sleep(0.05); print('second-result'); sys.exit(3)",
            ],
            [sys.executable, "-c", "print('third-result')"],
        ]
        stream = io.StringIO()
        status = VALIDATOR.run_parallel(
            commands, os.environ.copy(), workers=3, stream=stream
        )
        output = stream.getvalue()
        self.assertEqual(7, status)
        self.assertLess(output.index("first-result"), output.index("second-result"))
        self.assertLess(output.index("second-result"), output.index("third-result"))

    def test_worker_one_and_four_keep_identical_failure_order(self):
        commands = [
            [sys.executable, "-c", "import sys; print('alpha'); sys.exit(6)"],
            [sys.executable, "-c", "import sys; print('beta'); sys.exit(4)"],
            [sys.executable, "-c", "print('gamma')"],
        ]
        outputs = []
        statuses = []
        for workers in (1, 4):
            stream = io.StringIO()
            statuses.append(
                VALIDATOR.run_parallel(
                    commands, os.environ.copy(), workers=workers, stream=stream
                )
            )
            outputs.append(stream.getvalue())
        self.assertEqual([6, 6], statuses)
        self.assertEqual(outputs[0], outputs[1])

    def test_success_and_failure_cleanup_detached_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            for exit_code in (0, 9):
                with self.subTest(exit_code=exit_code):
                    pid_file = Path(temporary) / f"child-{exit_code}.pid"
                    status = VALIDATOR.run_parallel(
                        [detached_child_command(pid_file, exit_code)],
                        os.environ.copy(),
                        workers=1,
                        stream=io.StringIO(),
                    )
                    wait_for_file(pid_file)
                    self.assertEqual(exit_code, status)
                    assert_process_exits(self, int(pid_file.read_text()))

    def test_interruption_cleanup_detached_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "interrupted.pid"
            cancel = threading.Event()
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(
                    VALIDATOR._capture,
                    detached_child_command(pid_file, linger=True),
                    os.environ.copy(),
                    cancel,
                )
                wait_for_file(pid_file)
                cancel.set()
                completed = result.result(timeout=5)
            self.assertEqual(130, completed.returncode)
            assert_process_exits(self, int(pid_file.read_text()))

    @unittest.skipIf(os.name == "nt", "SIGINT delivery is POSIX-specific")
    def test_run_parallel_sigint_cleans_detached_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "sigint.pid"
            command = detached_child_command(pid_file, linger=True)
            script = (
                "import importlib.util,io,os; "
                f"spec=importlib.util.spec_from_file_location('validator',{str(ROOT / 'scripts/validate-public.py')!r}); "
                "validator=importlib.util.module_from_spec(spec); spec.loader.exec_module(validator); "
                f"validator.run_parallel([{command!r}],os.environ.copy(),1,io.StringIO())"
            )
            runner = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wait_for_file(pid_file)
            os.kill(runner.pid, signal.SIGINT)
            runner.wait(timeout=5)
            self.assertNotEqual(0, runner.returncode)
            assert_process_exits(self, int(pid_file.read_text()))

    def test_windows_cleanup_uses_a_kill_on_close_job_without_taskkill(self):
        source = (ROOT / "scripts" / "validate-public.py").read_text(encoding="utf-8")
        self.assertIn("CreateJobObjectW.restype = wintypes.HANDLE", source)
        self.assertIn("AssignProcessToJobObject.argtypes", source)
        self.assertIn("0x00002000", source)
        self.assertNotIn("taskkill", source.casefold())

    @unittest.skipIf(
        os.environ.get("CLONAMIC_ROOT_SUITE_ACTIVE") == "1",
        "avoid recursive root-suite verification",
    )
    def test_root_suite_is_readonly_under_parallel_supervision(self):
        command = VALIDATOR.build_plan()["packages"][0]
        before = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        env = {**os.environ, "CLONAMIC_ROOT_SUITE_ACTIVE": "1"}
        status = VALIDATOR.run_parallel(
            [command], env, workers=1, stream=io.StringIO()
        )
        after = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(0, status)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
