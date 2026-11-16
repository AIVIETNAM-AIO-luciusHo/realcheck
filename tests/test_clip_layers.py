"""models/clip_layers.py bằng CLIPVisionConfig nhỏ khởi tạo ngẫu nhiên: không tải trọng số, không dùng mạng."""

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from models import clip_layers

HIDDEN, LAYERS = 16, 3


@pytest.fixture(scope="module")
def tiny():
    config = transformers.CLIPVisionConfig(
        hidden_size=HIDDEN,
        intermediate_size=32,
        num_hidden_layers=LAYERS,
        num_attention_heads=2,
        image_size=32,
        patch_size=16,
        projection_dim=8,
    )
    torch.manual_seed(0)
    model = transformers.CLIPVisionModel(config).eval()
    processor = transformers.CLIPImageProcessor(
        size={"shortest_edge": 32}, crop_size={"height": 32, "width": 32}
    )
    return model, processor


def images(n=3):
    rng = np.random.default_rng(0)
    return [
        Image.fromarray(rng.integers(0, 256, (40, 48, 3), dtype=np.uint8), "RGB")
        for _ in range(n)
    ]


def test_shape_noi_va_rieng(tiny):
    model, processor = tiny
    imgs = images(3)
    cat = clip_layers.extract_features(imgs, model, processor, [1, 3])
    sep = clip_layers.extract_features(imgs, model, processor, [1, 3], concat=False)
    assert cat.shape == (3, 2 * HIDDEN) and sep.shape == (3, 2, HIDDEN)
    assert np.allclose(cat, sep.reshape(3, -1))


def test_tat_dinh(tiny):
    model, processor = tiny
    a = clip_layers.extract_features(images(), model, processor, [2, -1])
    b = clip_layers.extract_features(images(), model, processor, [2, -1])
    assert np.array_equal(a, b)


def test_thu_tu_lop_va_so_am(tiny):
    model, processor = tiny
    imgs = images(2)
    ab = clip_layers.extract_features(imgs, model, processor, [1, 3], concat=False)
    ba = clip_layers.extract_features(imgs, model, processor, [3, 1], concat=False)
    assert np.array_equal(ab[:, 0], ba[:, 1]) and np.array_equal(ab[:, 1], ba[:, 0])
    assert not np.allclose(ab[:, 0], ab[:, 1])  # hai lớp khác nhau cho CLS khác nhau
    last = clip_layers.extract_features(imgs, model, processor, [-1], concat=False)
    assert np.array_equal(last[:, 0], ab[:, 1])  # -1 là khối cuối = lớp 3


def test_cls_dung_la_token_dau_cua_hidden_states(tiny):
    model, processor = tiny
    pixels = processor(images=images(2), return_tensors="pt")["pixel_values"]
    with torch.no_grad():
        hidden = model(pixel_values=pixels, output_hidden_states=True).hidden_states
    out = clip_layers.cls_by_layer(model, pixels, [2], concat=False)
    assert np.allclose(out[:, 0], hidden[2][:, 0, :].numpy())
    assert len(hidden) == LAYERS + 1


def test_chia_lo_khong_doi_ket_qua(tiny):
    model, processor = tiny
    imgs = images(5)
    full = clip_layers.extract_features(imgs, model, processor, [3], batch_size=32)
    split = clip_layers.extract_features(imgs, model, processor, [3], batch_size=2)
    assert np.allclose(full, split, atol=1e-5)


def test_l2_va_post_layernorm(tiny):
    model, processor = tiny
    out = clip_layers.extract_features(
        images(), model, processor, [1, 2], concat=False, l2_normalize=True
    )
    assert np.allclose(np.linalg.norm(out, axis=-1), 1, atol=1e-5)
    plain = clip_layers.extract_features(images(), model, processor, [3], concat=False)
    ln = clip_layers.extract_features(
        images(), model, processor, [3], concat=False, post_layernorm=True
    )
    assert not np.allclose(plain, ln)


@pytest.mark.parametrize("layers", [[], [4], [-5], [1, 1], [1, -3], [1.5], [True]])
def test_lop_khong_hop_le(layers):
    with pytest.raises((ValueError, TypeError)):
        clip_layers.resolve_layers(layers, LAYERS)


def test_batch_size_va_anh_rong(tiny):
    model, processor = tiny
    with pytest.raises(ValueError, match="batch_size"):
        clip_layers.extract_features(images(), model, processor, [1], batch_size=0)
    with pytest.raises(ValueError, match="không có ảnh"):
        clip_layers.extract_features([], model, processor, [1])


def test_inputs_follow_model_device_without_gpu(tiny, monkeypatch):
    from types import SimpleNamespace

    _, processor = tiny
    model = SimpleNamespace(parameters=lambda: iter([torch.empty(1, device="meta")]))

    def capture(model, pixels, layers, **options):
        assert pixels.device.type == "meta"
        return np.zeros((pixels.shape[0], HIDDEN), dtype=np.float32)

    monkeypatch.setattr(clip_layers, "cls_by_layer", capture)
    assert clip_layers.extract_features(images(2), model, processor, [1]).shape == (
        2,
        HIDDEN,
    )
