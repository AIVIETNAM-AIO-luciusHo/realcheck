"""Run identity stays distinct even when the host clock has repeated values."""

from datetime import UTC, datetime
from unittest.mock import Mock

from models import run_info


def test_repeated_clock_does_not_reuse_run_id(monkeypatch):
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


def test_missing_git_is_recorded_as_unknown(monkeypatch):
    monkeypatch.setattr(
        run_info.subprocess, "check_output", Mock(side_effect=FileNotFoundError)
    )
    result = run_info.run_info("models.train")
    assert result["git_commit"] is None and result["git_dirty"] is None
