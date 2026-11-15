"""scripts/soak_rss.py: lấy mẫu RSS bằng docker giả, ghi file mà check_performance đọc được."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts import soak_rss
from scripts.check_performance import evaluate_rss


class FakeClock:
    """Giờ giả: sleep chỉ cộng thời gian, nên test chạy tức thì."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def __call__(self):
        return self.t


def run_collect(values, duration, warmup, interval=30):
    clk, it = FakeClock(), iter(values)
    return soak_rss.collect(
        lambda: next(it), duration, warmup, interval, clk.sleep, clk
    )


@pytest.mark.parametrize(
    ("text", "mib"),
    [
        ("543.2MiB / 2GiB", 543.2),
        ("1GiB / 2GiB", 1024.0),
        ("512KiB / 2GiB", 0.5),
        ("1048576B / 2GiB", 1.0),
        ("500MB / 2GB", 500 * 10**6 / 2**20),
    ],
)
def test_parse_mem_usage_don_vi(text, mib):
    assert soak_rss.parse_mem_usage(text) == pytest.approx(mib)


@pytest.mark.parametrize("bad", ["", "abc", "12XB / 2GiB", "543MiB"])
def test_parse_mem_usage_loi(bad):
    with pytest.raises(ValueError):
        soak_rss.parse_mem_usage(bad)


def test_collect_lay_mau_dung_moc():
    # duration 120, interval 30 => mẫu ở 0, 30, 60, 90, 120; warmup 60 => đầu tiên là 60
    result, samples = run_collect([100, 110, 120, 130, 140], duration=120, warmup=60)
    assert [t for t, _ in samples] == [0, 30, 60, 90, 120]
    assert result == {"rss_after_warmup_mb": 120, "rss_end_mb": 140}


def test_collect_mau_cuoi_dung_cuoi_thoi_luong():
    # duration không chia hết interval: mẫu cuối vẫn ở đúng 100 s
    _, samples = run_collect([1, 2, 3, 4, 5], duration=100, warmup=30)
    assert [t for t, _ in samples][-1] == 100


@pytest.mark.parametrize(
    ("duration", "warmup", "interval"),
    [(60, 60, 30), (30, 60, 30), (60, -1, 30), (60, 0, 0)],
)
def test_collect_tham_so_sai(duration, warmup, interval):
    with pytest.raises(ValueError):
        run_collect([1] * 10, duration, warmup, interval)


def test_collect_can_it_nhat_hai_mau_sau_warmup():
    with pytest.raises(ValueError, match="2 mẫu"):
        run_collect([1, 2, 3], duration=60, warmup=60 - 1, interval=60)


def test_main_ghi_file_check_performance_doc_duoc(tmp_path, monkeypatch):
    clk = FakeClock()
    monkeypatch.setattr(soak_rss.time, "sleep", clk.sleep)
    monkeypatch.setattr(soak_rss.time, "monotonic", clk)
    out = tmp_path / "sub" / "rss.json"
    vals = iter([400.0, 410.0, 420.0, 440.0, 462.0])
    argv = ["--container", "c", "--duration-seconds", "120", "--warmup-seconds", "30"]
    assert soak_rss.main([*argv, "--output", str(out)], read=lambda: next(vals)) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {"rss_after_warmup_mb", "rss_end_mb"}
    assert data == {"rss_after_warmup_mb": 410.0, "rss_end_mb": 462.0}
    # loader thật của check_performance: tăng 12.68% so với ngưỡng 10 thì báo lỗi
    assert evaluate_rss(out, {"rss_growth_pct_max": 10})
    assert evaluate_rss(out, {"rss_growth_pct_max": 15}) == []


def test_main_docker_loi_thoat_2_va_khong_ghi_file(tmp_path, capsys):
    def fail():
        raise ValueError("docker stats lỗi")

    out = tmp_path / "rss.json"
    argv = ["--container", "c", "--duration-seconds", "60", "--warmup-seconds", "0"]
    assert soak_rss.main([*argv, "--output", str(out)], read=fail) == 2
    assert not out.exists()
    assert "LỖI" in capsys.readouterr().err


def test_docker_mem_mib_goi_dung_lenh_va_bao_loi():
    calls = []

    def ok(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="543.2MiB / 2GiB\n", stderr="")

    assert soak_rss.docker_mem_mib("realcheck-api-1", run=ok) == pytest.approx(543.2)
    assert (
        calls[0][:3] == ["docker", "stats", "--no-stream"]
        and calls[0][-1] == "realcheck-api-1"
    )

    def no_container(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="No such container")

    with pytest.raises(ValueError, match="No such container"):
        soak_rss.docker_mem_mib("x", run=no_container)

    def no_docker(cmd, **kw):
        raise FileNotFoundError("docker")

    with pytest.raises(ValueError, match="docker"):
        soak_rss.docker_mem_mib("x", run=no_docker)
    assert subprocess  # run mặc định là subprocess.run, không gọi thật trong test này
