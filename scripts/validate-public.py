#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command, env):
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def main():
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    env["CLONAMIC_OFFLINE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = [
        [sys.executable, "scripts/generate-adapters.py", "--check"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    ]
    for package_tests in sorted(ROOT.glob("plugins/*/tests")):
        if any(package_tests.glob("test*.py")):
            commands.append(
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
    commands.append(
        [
            sys.executable,
            "plugins/clonamic-ppt/skills/clonamic-ppt/tests/run_all.py",
        ]
    )
    commands.extend(
        [
            ["cargo", "fmt", "--check"],
            ["cargo", "check", "--all-targets"],
            ["cargo", "clippy", "--all-targets", "--", "-D", "warnings"],
            ["cargo", "test", "--all-targets"],
        ]
    )
    for command in commands:
        status = run(command, env)
        if status != 0:
            return status
    print(f"validation passed: {len(commands)} local commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
