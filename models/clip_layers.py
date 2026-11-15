"""Trích CLS của NHIỀU lớp ViT trong CLIP (CLIPVisionModel) cho thí nghiệm ADV-12 (#144). THỬ NGHIỆM.

Không dùng cho model phục vụ: đặc trưng ở đây KHÔNG cùng không gian với `models.clip_input` (bản đóng băng của
e571), nên không thể đưa vào probe e571 hay `models.score`. Mục đích duy nhất: thử xem đặc trưng từ lớp giữa có
phân biệt tốt hơn trên ảnh điện thoại/Zalo không, rồi so bằng `scripts.compare_models`.

`layers` đánh số theo `hidden_states` của transformers: 0 là đầu ra embedding, 1..N là đầu ra các khối
(N = `num_hidden_layers`); chấp nhận số âm như chỉ số Python (-1 là khối cuối). CLS lấy trước `post_layernorm`
(khác `pooler_output`); đặt `post_layernorm=True` để áp lớp đó cho từng CLS.
"""

import numpy as np

DEFAULT_MODEL_ID = "openai/clip-vit-base-patch32"


def load_vision_model(
    model_id: str = DEFAULT_MODEL_ID, revision: str | None = None, device: str = "cpu"
):
    """CLIPVisionModel + CLIPImageProcessor; TẢI trọng số từ Hugging Face (cần mạng hoặc cache), ở chế độ eval.

    Ví dụ ViT-L/14: `load_vision_model("openai/clip-vit-large-patch14", revision=<commit>)`. Hãy ghim `revision`.
    """
    from transformers import CLIPImageProcessor, CLIPVisionModel

    model = (
        CLIPVisionModel.from_pretrained(model_id, revision=revision).to(device).eval()
    )
    model.requires_grad_(False)
    return model, CLIPImageProcessor.from_pretrained(model_id, revision=revision)


def resolve_layers(layers: list[int], num_hidden_layers: int) -> list[int]:
    """Chuẩn hóa chỉ số lớp về 0..N (N = num_hidden_layers); ValueError nếu rỗng, trùng hoặc ngoài khoảng; TypeError nếu không phải số nguyên."""
    if not layers:
        raise ValueError("layers không được rỗng")
    resolved = []
    for layer in layers:
        if isinstance(layer, bool) or not isinstance(layer, int):
            raise TypeError(f"chỉ số lớp phải là số nguyên: {layer!r}")
        index = layer + num_hidden_layers + 1 if layer < 0 else layer
        if not 0 <= index <= num_hidden_layers:
            raise ValueError(
                f"lớp {layer} ngoài khoảng [0, {num_hidden_layers}] (hoặc số âm tương ứng)"
            )
        resolved.append(index)
    if len(set(resolved)) != len(resolved):
        raise ValueError("layers có lớp trùng")
    return resolved


def cls_by_layer(
    model,
    pixel_values,
    layers: list[int],
    *,
    concat: bool = True,
    post_layernorm: bool = False,
    l2_normalize: bool = False,
) -> np.ndarray:
    """CLS của các lớp theo đúng thứ tự `layers`.

    Trả `(B, len(layers) * D)` khi `concat=True` (nối theo thứ tự `layers`), hoặc `(B, len(layers), D)` khi
    `concat=False`. `l2_normalize` chuẩn hóa L2 từng CLS trước khi nối. Không tính gradient.
    """
    import torch

    index = resolve_layers(layers, model.config.num_hidden_layers)
    with torch.no_grad():
        hidden = model(
            pixel_values=pixel_values, output_hidden_states=True
        ).hidden_states
        cls = torch.stack([hidden[i][:, 0, :] for i in index], dim=1)  # (B, L, D)
        if post_layernorm:
            cls = getattr(model, "vision_model", model).post_layernorm(
                cls
            )  # transformers 4 có vision_model, 5 thì không
        if l2_normalize:
            cls = torch.nn.functional.normalize(cls, dim=-1)
    out = cls.float().cpu().numpy()
    return out.reshape(out.shape[0], -1) if concat else out


def extract_features(
    images: list,
    model,
    processor,
    layers: list[int],
    *,
    batch_size: int = 32,
    **options,
) -> np.ndarray:
    """Chạy `processor` rồi `cls_by_layer` theo lô, giữ nguyên thứ tự ảnh; `options` chuyển cho `cls_by_layer`."""
    if batch_size < 1:
        raise ValueError("batch_size phải >= 1")
    batches = []
    for start in range(0, len(images), batch_size):
        pixels = processor(
            images=[im.convert("RGB") for im in images[start : start + batch_size]],
            return_tensors="pt",
        )
        batches.append(cls_by_layer(model, pixels["pixel_values"], layers, **options))
    if not batches:
        raise ValueError("không có ảnh")
    return np.concatenate(batches, axis=0)
