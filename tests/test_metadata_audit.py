"""metadata_audit.py chỉ cảnh báo A_eff cao (thoát 0); lỗi dữ liệu thoát 1. Ảnh tổng hợp."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from scripts import check_release_audit as cra
from scripts import metadata_audit as ma

ROOT = Path(__file__).resolve().parents[1]


def make(tmp_path, *, leak: bool, n=200, test=150):
    """leak=True: ở post, ảnh AI là JPEG và ảnh thật là PNG (format lộ nhãn); raw luôn JPEG."""
    rows = []
    for label in (0, 1):
        for i in range(n):
            ext = "png" if (label == 0 and leak) else "jpg"
            p = tmp_path / f"{label}_{i}.{ext}"
            Image.fromarray(np.zeros((8, 8 + i % 3, 3), np.uint8)).save(p)
            raw = tmp_path / f"raw_{label}_{i}.jpg"
            # raw có biến thiên không liên quan nhãn: HGB (sklearn 1.9) lỗi với cột toàn NaN
            Image.fromarray(np.zeros((8, 8 + i % 3, 3), np.uint8)).save(raw)
            rows.append(
                {
                    "raw_path": str(raw),
                    "filepath": str(p),
                    "label": label,
                    "source": "cifake_real" if label == 0 else "cifake_ai",
                    # test 150 mỗi lớp: nhãn xáo của control âm vẫn >= MIN_PER_CLASS, còn lại để train
                    "split": "test" if i < test else "train",
                }
            )
    pd.DataFrame(rows).to_csv(tmp_path / "labels.csv", index=False)


def run(tmp_path):
    # chạy ở tmp_path để LABELS_CSV/OUT_JSON tương đối trỏ vào data/ tạm
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "labels.csv").rename(tmp_path / "data" / "labels.csv")
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "metadata_audit.py")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",  # Windows mặc định cp1252, không giải mã được tiếng Việt
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_a_eff_cao_chi_canh_bao(tmp_path):
    make(tmp_path, leak=True)
    r = run(tmp_path)
    out = json.loads((tmp_path / "data" / "metadata_audit.json").read_text())
    assert out["cifake"]["slices"]["all"]["post"]["a_eff"] > 0.55
    assert out["gate"]["passed"] is False  # khóa cũ cho G02 giữ nguyên
    assert "CẢNH BÁO" in r.stdout
    assert "LỖI" not in r.stdout, r.stdout
    assert r.returncode == 0
    # đầu ra thật nối vào release checker: n_features đúng, không bị coi là rỗng
    assert out["cifake"]["n_features"] == 13 + 4  # metadata + pixel
    assert cra.vacuous(out) == []
    assert any("A_eff" in p for p in cra.problems(out))


def test_control_am_khong_hop_le_la_loi(tmp_path):
    # test đúng 100/lớp: slice post hợp lệ, nhưng nhãn xáo của control âm lệch dưới 100 (SEED cố định)
    make(tmp_path, leak=False, n=110, test=100)
    r = run(tmp_path)
    assert r.returncode == 1
    assert "control" in r.stdout


def test_slice_thieu_mau_la_loi(tmp_path):
    make(tmp_path, leak=False, n=60)  # < MIN_PER_CLASS mỗi lớp ở test
    r = run(tmp_path)
    assert r.returncode == 1
    assert "LỖI" in r.stdout


def fake_run(tmp_path, monkeypatch, post_a_eff):
    """Chạy main() với probe giả: chỉ ngưỡng MAX_A_EFF và nối JSON được kiểm."""
    pd.DataFrame(
        [
            {
                "raw_path": f"raw_{i}",
                "filepath": f"post_{i}",
                "label": i % 2,
                "source": "cifake_real" if i % 2 == 0 else "cifake_ai",
                "split": "test",
            }
            for i in range(4)
        ]
    ).to_csv(tmp_path / "labels.csv", index=False)
    monkeypatch.setattr(ma, "LABELS_CSV", tmp_path / "labels.csv")
    monkeypatch.setattr(ma, "OUT_JSON", tmp_path / "out.json")
    monkeypatch.setattr(
        ma,
        "extract",
        lambda p: {
            **{c: "x" for c in ma.CATEGORICAL},
            "width": 1,
            "post": p[:3] == "pos",
        },
    )

    def evaluate(x, y, split):
        a = 1.0 if "control" in x else (post_a_eff if x["post"].iloc[0] else 0.5)
        return {"valid": True, "test_counts": {0: 2, 1: 2}, "a_eff": a, "ci95": [a, a]}

    monkeypatch.setattr(ma, "pixel_features", lambda p: {})
    monkeypatch.setattr(ma, "evaluate", evaluate)
    with pytest.raises(SystemExit) as e:
        ma.main()
    return e.value.code, json.loads((tmp_path / "out.json").read_text())


@pytest.mark.parametrize("a, warns", [(0.54, False), (0.55, False), (0.56, True)])
def test_nguong_0_55_canh_bao(tmp_path, monkeypatch, capsys, a, warns):
    code, out = fake_run(tmp_path, monkeypatch, a)
    assert code == 0
    assert ("CẢNH BÁO" in capsys.readouterr().out) == warns
    assert out["gate"]["passed"] is (not warns)
    # JSON thật nối vào checker: chặn đúng khi vượt ngưỡng
    assert (cra.problems(out) != []) == warns


def test_pixel_features_do_dung_dau_vet(tmp_path):
    """Ảnh phẳng: không dấu khối, không tần số cao; khối 8×8 có dấu khối; nhiễu có tần
    số cao và nhiễu dư lớn hơn ảnh gradient mượt; PNG không nén mất dữ liệu."""
    rng = np.random.default_rng(0)
    images = {
        "flat": np.full((64, 64), 128),
        "blocks": np.kron(rng.integers(0, 256, (8, 8)), np.ones((8, 8))),
        "noise": rng.integers(0, 256, (64, 64)),
        "smooth": np.tile(np.linspace(0, 255, 64), (64, 1)),
    }
    f = {}
    for name, a in images.items():
        path = tmp_path / f"{name}.png"
        Image.fromarray(a.astype(np.uint8)).save(path)
        f[name] = ma.pixel_features(str(path))
        assert set(f[name]) == set(ma.PIXEL_FEATURES)
    assert f["flat"]["blockiness"] == pytest.approx(1.0)
    assert f["flat"]["hf_energy"] == 0.0 and f["flat"]["noise_std"] == 0.0
    assert f["blocks"]["blockiness"] > 100 * f["noise"]["blockiness"]
    assert f["noise"]["hf_energy"] > 10 * f["smooth"]["hf_energy"]
    assert f["noise"]["noise_std"] > 10 * f["smooth"]["noise_std"]
    assert f["noise"]["bytes_per_px"] > f["flat"]["bytes_per_px"]


def test_pixel_features_anh_nho_khong_loi(tmp_path):
    path = tmp_path / "tiny.png"
    Image.new("L", (2, 2)).save(path)
    f = ma.pixel_features(str(path))
    assert np.isnan(f["blockiness"]) and np.isnan(f["noise_std"])


def test_probe_pixel_bat_duoc_khi_metadata_hang_so(tmp_path):
    """Post: mọi ảnh cùng JPEG Q95 32×32 (13 đặc trưng metadata hằng số), chỉ khác nội dung
    pixel theo nhãn. Probe cũ ra 0.5 "rỗng"; probe pixel phải bắt được và checker chặn."""
    rng = np.random.default_rng(1)
    rows = []
    for label in (0, 1):
        for i in range(200):
            base = np.tile(np.linspace(0, 255, 32), (32, 1)) + rng.integers(0, 40)
            if label:
                base = base + rng.normal(0, 40, base.shape)
            rgb = np.repeat(np.clip(base, 0, 255)[..., None], 3, axis=2).astype(
                np.uint8
            )
            post = tmp_path / f"{label}_{i}.jpg"
            Image.fromarray(rgb).save(post, quality=95)
            raw = tmp_path / f"raw_{label}_{i}.jpg"  # raw biến thiên không theo nhãn
            Image.new("RGB", (8, 8 + i % 3)).save(raw)
            rows.append(
                {
                    "raw_path": str(raw),
                    "filepath": str(post),
                    "label": label,
                    "source": "cifake_real" if label == 0 else "cifake_ai",
                    "split": "test" if i < 150 else "train",
                }
            )
    pd.DataFrame(rows).to_csv(tmp_path / "labels.csv", index=False)
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    out = json.loads((tmp_path / "data" / "metadata_audit.json").read_text())
    c = out["cifake"]
    assert set(ma.FEATURES) <= set(c["constant_features"]["post"])
    assert not set(ma.PIXEL_FEATURES) & set(c["constant_features"]["post"])
    assert c["slices"]["all"]["post"]["a_eff"] > 0.9
    assert cra.vacuous(out) == []
    assert any("A_eff" in p for p in cra.problems(out))
