"""Test cho .github/scripts/check_freeze.py (CI-6)."""

import importlib.util
import json
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_freeze",
    pathlib.Path(__file__).resolve().parents[1] / ".github/scripts/check_freeze.py",
)
cf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cf)


def test_pr_chi_sua_docs_vuot_khi_bat():
    ok, _ = cf.decide(["docs/a.md", "README.md", "tests/test_x.py"], [], True)
    assert ok


@pytest.mark.parametrize(
    "path",
    [
        "app/main.py",
        "nginx/nginx.conf",
        "models/x.py",
        "locust/locustfile.py",
        "scripts/a.py",
        "docker-compose.yml",
    ],
)
def test_pr_sua_thu_muc_dong_bang_khong_nhan_truot(path):
    ok, msg = cf.decide(["docs/a.md", path], [], True)
    assert not ok and path in msg


def test_co_nhan_override_vuot():
    ok, msg = cf.decide(["app/main.py"], ["bug", "freeze-override"], True)
    assert ok and "freeze-override" in msg


def test_nhan_gan_giong_khong_tinh():
    ok, _ = cf.decide(["app/main.py"], ["freeze-override-x", "freeze"], True)
    assert not ok


def test_freeze_tat_thi_khong_chan():
    ok, _ = cf.decide(["app/main.py"], [], False)
    assert ok


def test_khong_nham_ten_tuong_tu():
    # docker-compose.monitoring.yml, scripts_old/, application/ không thuộc đóng băng
    assert (
        cf.frozen_paths(
            [
                "docker-compose.monitoring.yml",
                "scripts_old/a",
                "application/x",
                "docs/app/x.md",
            ]
        )
        == []
    )


def test_doi_ten_tinh_ca_duong_dan_cu():
    # workflow dùng --no-renames nên đường dẫn cũ xuất hiện như file bị xóa
    assert cf.frozen_paths(["app/old.py", "docs/new.py"]) == ["app/old.py"]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("enabled: true", True),
        ("# c\nEnabled: TRUE  # ghi chú", True),
        ("enabled: 'true'", True),
        ("enabled: false", False),
        ("", False),
        ("enabled: yes", False),
        ("# enabled: true", False),
    ],
)
def test_parse_enabled(text, want):
    assert cf.parse_enabled(text) is want


def _run(tmp_path, monkeypatch, files, labels, var="", freeze_text=None):
    f = tmp_path / "changed.txt"
    f.write_text("\n".join(files), encoding="utf-8")
    monkeypatch.setenv("LABELS", json.dumps(labels))
    monkeypatch.setenv("FREEZE_VAR", var)
    args = ["--files", str(f)]
    if freeze_text is not None:
        fz = tmp_path / "freeze.yml"
        fz.write_text(freeze_text, encoding="utf-8")
        args += ["--freeze-file", str(fz)]
    return cf.main(args)


def test_main_bat_bang_bien_repo(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, ["app/a.py"], [], var="true") == 1
    assert _run(tmp_path, monkeypatch, ["docs/a.md"], [], var="true") == 0


def test_main_bat_bang_file_cua_nhanh_goc(tmp_path, monkeypatch):
    assert (
        _run(tmp_path, monkeypatch, ["scripts/a.py"], [], freeze_text="enabled: true")
        == 1
    )
    assert (
        _run(
            tmp_path,
            monkeypatch,
            ["scripts/a.py"],
            ["freeze-override"],
            freeze_text="enabled: true",
        )
        == 0
    )


def test_main_mac_dinh_tat(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, ["app/a.py"], []) == 0


def test_main_labels_hong_thoat_2(tmp_path, monkeypatch):
    f = tmp_path / "c.txt"
    f.write_text("app/a.py", encoding="utf-8")
    monkeypatch.setenv("LABELS", "{không phải json")
    assert cf.main(["--files", str(f)]) == 2


def test_workflow_freeze_khong_vao_ci_ok_va_khong_dung_target():
    root = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows"
    wf = (root / "freeze.yml").read_text(encoding="utf-8")
    assert "pull_request_target" not in wf
    assert "contents: read" in wf
    assert (
        "freeze"
        not in (root / "ci.yml").read_text(encoding="utf-8").lower().split("ci-ok:")[1]
    )
