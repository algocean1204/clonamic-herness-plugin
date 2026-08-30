"""Run LibreOffice without modifying the host process environment."""

from __future__ import annotations

import os
import subprocess


def get_soffice_env() -> dict[str, str]:
    """Return a headless LibreOffice environment without native injection."""
    env = os.environ.copy()
    env["SAL_USE_VCLPLUGIN"] = "svp"
    return env


def run_soffice(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run an installed LibreOffice CLI with caller-owned timeout and capture."""
    return subprocess.run(["soffice", *args], env=get_soffice_env(), **kwargs)


if __name__ == "__main__":
    import sys

    raise SystemExit(run_soffice(sys.argv[1:]).returncode)
