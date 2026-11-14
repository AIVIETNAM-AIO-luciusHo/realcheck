"""Run identity stays distinct even when the host clock has repeated values."""

import hashlib
from datetime import UTC, datetime
from unittest.mock import Mock

from models import run_info


def test_repeated_clock_does_not_reuse_run_id(monkeypatch):
    # platform.platform() may call subprocess and consume the Git mock results.
    monkeypatch.setattr(
        run_info.platform, "platform", Mock(return_value="test-platform")
    )
    monkeypatch.setattr(
        run_info,
        "datetime",
        Mock(now=Mock(return_value=datetime(2026, 11, 5, tzinfo=UTC))),
    )
    monkeypatch.setattr(
        run_info.subprocess,
        "check_output",
        Mock(side_effect=["a" * 40, "", "a" * 40, ""]),
    )
    first, second = run_info.run_info("models.train"), run_info.run_info("models.train")
    assert first["started_at"] == second["started_at"]
    assert first["id"] != second["id"]
    assert first["git_commit"] == "a" * 40 and first["git_dirty"] is False
    assert second["git_commit"] == "a" * 40 and second["git_dirty"] is False


def test_missing_git_is_recorded_as_unknown(monkeypatch):
    monkeypatch.setattr(
        run_info.platform, "platform", Mock(return_value="test-platform")
    )
    monkeypatch.setattr(
        run_info.subprocess, "check_output", Mock(side_effect=FileNotFoundError)
    )
    result = run_info.run_info("models.train")
    assert result["git_commit"] is None and result["git_dirty"] is None


def test_environment_hashes_a_sorted_pep503_package_list(monkeypatch):
    dists = [
        Mock(metadata={"Name": "Scikit_Learn"}, version="1.9.1"),
        Mock(metadata={"Name": "numpy"}, version="2.4.6"),
        Mock(metadata={"Name": "numpy"}, version="2.4.6"),  # same dist on two paths
        Mock(metadata={"Name": None}, version="0"),
    ]
    monkeypatch.setattr(run_info.metadata, "distributions", Mock(return_value=dists))
    env = run_info.environment()
    assert env["packages"] == ["numpy==2.4.6", "scikit-learn==1.9.1"]
    listing = b"numpy==2.4.6\nscikit-learn==1.9.1\n"
    assert env["packages_sha256"] == hashlib.sha256(listing).hexdigest()
    assert env["python"] == run_info.platform.python_version()
