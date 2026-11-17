# Phụ thuộc khai báo ở nhiều file

Một số phiên bản nằm ở nhiều nơi và phải đổi **cùng một PR**. `tests/test_dependency_pins.py` (và `tests/test_docker_static.py`) đọc giá trị từ chính các file và đỏ khi chỉ đổi một nơi; nâng đồng thời ở mọi nơi vẫn xanh.

| Phụ thuộc | Nơi khai báo | Test khóa |
|---|---|---|
| Python | `Dockerfile` (`FROM python:X-slim`), `streamlit/Dockerfile`, job `test` và `lint` trong `.github/workflows/ci.yml` | `test_docker_static` (Dockerfile và ci.yml), `test_dependency_pins` (hai Dockerfile) |
| ruff | `requirements.txt`, `.github/workflows/ci.yml` (`pip install ruff==`), `.pre-commit-config.yaml` (`rev: vX`) | `test_ruff_cung_phien_ban_o_ba_noi` |
| torch | `models/requirements-ml.txt`, `Dockerfile` (cài từ index CPU) | `test_docker_static` |
| numpy, pillow, pandas, scikit-learn, joblib, huggingface-hub, httpx | nhiều file `requirements*.txt` (xem test) | `test_goi_xuat_hien_o_nhieu_file_requirements_phai_cung_phien_ban` |
| CLIP revision | `models/clip_input.py` (`CLIP_REVISION`, một nơi) | `test_clip_revision_la_sha_day_du_o_mot_noi` |

Ghi chú:
- Job `test-full` (khi có) được dùng Python khác job `test`; `test_docker_static` chỉ so Dockerfile với job `lint`/`test`.
- Nhóm gói gắn với model e571 (numpy, scikit-learn, pillow, joblib, pandas, torch, transformers, sentence-transformers, huggingface-hub, CLIP revision) **không đổi vì tự động hóa**: đổi là PR riêng, kèm kiểm lại model và bằng chứng nghiệm thu.
