# Biên bản kiểm thử tích hợp localhost (KAN-29, Q5)

Sao chép file này thành `docs/qa/integration-report-<ngày>.md` và điền. Người kiểm KHÁC người viết code của bản đang kiểm. Không tự coi mọi ảnh mẫu phải được phân loại đúng: mục tiêu là luồng chạy đúng hợp đồng, không phải độ chính xác model.

## 1. Môi trường

| Mục | Giá trị |
|---|---|
| Ngày, người kiểm | |
| Commit (`git rev-parse HEAD`), trạng thái dirty | |
| Nhánh | |
| Hệ điều hành, Python | |
| Phiên bản FastAPI, Pillow, uvicorn (`pip freeze`) | |
| Model: tệp, sha256 (`models/*.joblib.sha256`) | |
| Profile chuẩn hóa / `NORMALIZATION_VERSION` | |
| Biến `REALCHECK_*` đã đặt | |
| Lệnh khởi động | `uvicorn app.main:app --port 8000` |

## 2. Chuẩn bị

```bash
python -m scripts.make_fixtures --out .cache/smoke-fixtures
python -m scripts.smoke_api --base-url http://localhost:8000 --fixtures .cache/smoke-fixtures \
  --real <ảnh thật> --ai <ảnh AI> --out .cache/smoke-evidence.json
```

Ảnh `--real` và `--ai`: ghi nguồn, giấy phép. Không commit ảnh.

## 3. Acceptance Criteria

| AC | Nội dung | Kết quả (Đạt / Không / Chưa) | Bằng chứng |
|---|---|---|---|
| 1 | `/health` và `/docs` hoạt động | | |
| 2 | Gửi được ảnh thật và ảnh AI qua `/v1/analyze` | | |
| 3 | Response đúng schema (verdict, score, exif, reason), score trong [0,1] | | |
| 4 | Đầu vào không hợp lệ được xử lý đúng mã lỗi và HTTP (D05) | | |
| 5 | Chạy lại pytest, ghi coverage | | |
| 6 | Ghi lỗi còn tồn tại; lỗi chặn demo đã xử lý | | |

## 4. Kết quả smoke

Mã thoát của `smoke_api`: ___ (0 đạt, 1 có ca lỗi, 2 không kết nối/timeout/thiếu fixture). Ghi các cờ đã dùng (`--no-docs`, `--skip-size-boundary` làm AC tương ứng thành Chưa). Ca 5.242.880 byte lỗi thì cần xác nhận cách tính dung lượng của API/gateway. Đính kèm JSON bằng chứng.

| Ca | Kỳ vọng | Thực tế | Đạt / Lỗi |
|---|---|---|---|
| | | | |

Ảnh `--real` và `--ai` (chỉ ghi nhận, không phải tiêu chí đạt/lỗi):

| Ảnh | Nguồn | verdict | score | Nhận xét |
|---|---|---|---|---|
| thật | | | | |
| AI | | | | |

## 5. Pytest và coverage

```text
pytest --cov=app --cov-fail-under=70
(dán nguyên văn kết quả: số test pass/fail/skip, % coverage của app/)
```

## 6. Lỗi còn tồn tại

Mỗi lỗi điền theo [`docs/bug-report-template.md`](../bug-report-template.md) (file này nằm trong `.gitignore` nên không có trên GitHub: dán nội dung mô tả lỗi trực tiếp vào biên bản hoặc ticket) và ghi mã Jira.

| Mã Jira | Tóm tắt | Mức độ | Chặn demo? | Người xử lý | Trạng thái |
|---|---|---|---|---|---|
| | | | | | |

## 7. Xác nhận lỗi chặn demo

- [ ] Không còn lỗi mức Nghiêm trọng hoặc Cao chặn demo; hoặc từng lỗi còn lại có cách tránh được ghi rõ.
- [ ] Các lỗi chặn đã sửa được chạy lại smoke và pytest sau khi sửa (ghi commit sửa: ___).

## 8. Chữ ký

| Vai trò | Họ tên | Ngày |
|---|---|---|
| Người viết code bản kiểm | | |
| Người kiểm (khác người viết code) | | |
