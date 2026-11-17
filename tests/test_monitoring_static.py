"""Profile monitoring (#163, #164): không bật mặc định, không mở cổng, không đổi Compose core."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MON = yaml.safe_load(
    (ROOT / "docker-compose.monitoring.yml").read_text(encoding="utf-8")
)
CORE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_chi_co_prometheus_va_grafana_trong_profile_monitoring():
    assert set(MON["services"]) == {"prometheus", "grafana"}
    for svc in MON["services"].values():
        assert svc["profiles"] == ["monitoring"]


def test_khong_mo_cong_ra_may_chu():
    for svc in MON["services"].values():
        assert "ports" not in svc
    assert [k for k, v in CORE["services"].items() if "ports" in v] == ["nginx"]


def test_co_gioi_han_tai_nguyen_va_image_ghim_phien_ban():
    for svc in MON["services"].values():
        assert svc["cpus"] and svc["mem_limit"]
        assert ":" in svc["image"] and not svc["image"].endswith(":latest")


def test_compose_core_khong_nhac_monitoring():
    assert not {"prometheus", "grafana"} & set(CORE["services"])
    assert "monitoring" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_prometheus_cao_api_metrics():
    cfg = yaml.safe_load(
        (ROOT / "monitoring/prometheus.yml").read_text(encoding="utf-8")
    )
    job = cfg["scrape_configs"][0]
    assert job["metrics_path"] == "/metrics"
    assert job["static_configs"][0]["targets"] == ["api:8000"]


def test_thieu_mat_khau_grafana_khong_lam_hong_compose_config():
    text = (ROOT / "docker-compose.monitoring.yml").read_text(encoding="utf-8")
    assert (
        "REALCHECK_GRAFANA_PASSWORD:?" not in text
    )  # `:?` làm `config`/`down` lỗi khi chưa đặt biến
    assert "${REALCHECK_GRAFANA_PASSWORD:-}" in text
    entry = " ".join(MON["services"]["grafana"]["entrypoint"])
    assert (
        "-n" in entry and "exit 1" in entry
    )  # mật khẩu rỗng thì Grafana từ chối chạy (tránh admin/admin)
