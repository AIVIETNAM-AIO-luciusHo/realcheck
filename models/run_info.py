"""Record the executable, source checkout and environment of an ML CLI run."""

import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def run_info(module: str) -> dict:
    """Timestamps are descriptive; UUID and artifact hashes identify each run."""
    root = Path(__file__).resolve().parents[1]
    git = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root)]
    commit = dirty = None
    try:
        commit = subprocess.check_output(
            [*git, "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
        ).strip()
        dirty = bool(
            subprocess.check_output(
                [*git, "status", "--porcelain", "--untracked-files=normal"],
                text=True,
                stderr=subprocess.PIPE,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        # Source archives may have no Git metadata; never invent a commit.
        pass
    return {
        "id": str(uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "command": [sys.executable, "-m", module, *sys.argv[1:]],
        "working_directory": str(Path.cwd()),
        "git_commit": commit,
        "git_dirty": dirty,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
