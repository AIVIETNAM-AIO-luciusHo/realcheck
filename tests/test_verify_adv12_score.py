import pytest

from scripts import verify_adv12_score as v


@pytest.mark.parametrize(
    ("got", "expected", "tol", "ok"),
    [
        (0.9993029832839966, 0.9993029832839966, 1e-6, True),
        (0.9993039, 0.9993029832839966, 1e-6, True),
        (0.99931, 0.9993029832839966, 1e-6, False),
        (float("nan"), 0.5, 1e-6, False),
        (0.5, 0.5, -1.0, False),
        (0.5, 0.5, float("inf"), False),
    ],
)
def test_within_tolerance(got, expected, tol, ok):
    assert v.within_tolerance(got, expected, tol) is ok


def _run(monkeypatch, score, *extra):
    monkeypatch.setattr(v, "score_image", lambda m, i: score)
    return v.main(["--model", "m", "--image", "i", "--expected", "0.5", *extra])


def test_main_khop_va_lech(monkeypatch, capsys):
    assert _run(monkeypatch, 0.5 + 1e-7) == 0
    assert "KHỚP" in capsys.readouterr().out
    assert _run(monkeypatch, 0.6) == 1
    assert _run(monkeypatch, 0.6, "--tolerance", "0.2") == 0


def test_main_loi_dau_vao(monkeypatch, capsys):
    assert _run(monkeypatch, 0.5, "--tolerance", "-1") == 2

    def boom(m, i):
        raise FileNotFoundError("không có model")

    monkeypatch.setattr(v, "score_image", boom)
    assert v.main(["--model", "m", "--image", "i", "--expected", "0.5"]) == 2
    assert "Không chấm được" in capsys.readouterr().err


def test_thieu_doi_so():
    with pytest.raises(SystemExit) as e:
        v.main(["--model", "m"])
    assert e.value.code == 2
