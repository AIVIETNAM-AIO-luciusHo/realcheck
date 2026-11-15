"""Record the executable, source checkout and environment of an ML CLI run."""

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
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


def environment() -> dict:
    """Python version and installed packages, to pin a run's environment in a protocol.

    ``packages`` lists ``name==version`` like ``pip freeze`` (PEP 503 names, sorted);
    ``packages_sha256`` hashes that list, one entry per line.
    """
    packages = sorted(
        {
            f"{re.sub(r'[-_.]+', '-', name).lower()}=={dist.version}"
            for dist in metadata.distributions()
            if (name := dist.metadata["Name"])
        }
    )
    listing = "".join(f"{package}\n" for package in packages)
    return {
        "python": platform.python_version(),
        "packages": packages,
        "packages_sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
    }


if __name__ == "__main__":
    # Values for a protocol's "environment" field: python -m models.run_info
    env = environment()
    print(
        json.dumps({key: env[key] for key in ("python", "packages_sha256")}, indent=2)
    )
