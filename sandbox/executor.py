"""Local, subprocess-based sandboxed code execution (no cloud).

Not a full container/VM sandbox — this is deliberately lightweight per the
brief's "local subprocess-based sandboxed execution" scope. It mitigates the
common local-execution risks:
  - runs in an isolated temp directory (no access to project files)
  - hard wall-clock timeout (kills runaway/infinite-loop code)
  - stripped-down environment variables (no inherited secrets/API keys)
  - best-effort CPU time + memory rlimits on POSIX systems

It does NOT protect against a determined malicious actor (no network
namespace isolation, no seccomp). That tradeoff is called out in the
README's Limitations section.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from graph.state import TestResult

DEFAULT_TIMEOUT_SECONDS = 15
_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024  # 512 MB
_CPU_LIMIT_SECONDS = 15


def _limit_resources() -> None:
    """preexec_fn: apply best-effort rlimits on POSIX. No-op on Windows."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SECONDS, _CPU_LIMIT_SECONDS))
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
    except Exception:
        pass


def execute_code(code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> TestResult:
    """Write `code` to a temp file and execute it with the current interpreter.

    Returns a TestResult with pass/fail based on exit code 0, plus captured
    stdout/stderr for the Reviewer/Tester to inspect.
    """
    with tempfile.TemporaryDirectory(prefix="macs_sandbox_") as tmpdir:
        script_path = Path(tmpdir) / "solution.py"
        script_path.write_text(code)

        minimal_env = {"PATH": "/usr/bin:/bin"}

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=minimal_env,
                preexec_fn=_limit_resources if sys.platform != "win32" else None,
            )
            return TestResult(
                passed=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired as e:
            return TestResult(
                passed=False,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\n[sandbox] execution timed out after {timeout}s",
                exit_code=-1,
            )
