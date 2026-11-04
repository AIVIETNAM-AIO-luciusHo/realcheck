## Task liên quan

- **Jira:** KAN-
- **Task spec:** T___ (spec ___; ghi `Không có` nếu không thuộc spec nào)
- **Phụ thuộc / thứ tự merge:** <!-- PR hoặc nhánh phải merge trước; ghi `Không` nếu độc lập -->

## Loại thay đổi

<!-- Chọn MỘT. Tiêu đề PR theo dạng `loại: tóm tắt ngắn` (tiếng Anh). -->
- [ ] feat   - [ ] fix   - [ ] docs   - [ ] chore   - [ ] test

## Mô tả

**Làm gì và vì sao:**

**Không làm (ngoài phạm vi PR này):**

## Kết quả kiểm chứng

<!-- Dán lệnh đã chạy và kết quả thật (số test, coverage). Chưa chạy hoặc không chạy được thì ghi rõ lý do.
     CI xanh KHÔNG thay thế phần này: ghi số test thực sự chạy, có bị skip không. -->

```text
ruff check .            →
ruff format --check .   →
pytest -v               →  ___ passed, ___ failed, ___ skipped
pytest --cov=app --cov-fail-under=70   →  ___ %
```

**Cách reviewer chạy lại:**

## Giới hạn, rủi ro và việc chưa làm

<!-- Nói thẳng điều chưa kiểm được, điều còn giả định, task còn thiếu. Không ghi "đạt" cho số liệu chưa được QA kiểm độc lập. -->

## Phần theo loại thay đổi

<!-- Chỉ điền phần liên quan, xóa hoặc ghi N/A kèm lý do cho phần còn lại. -->

<details>
<summary><b>Code / API (app/, streamlit/, nginx/)</b></summary>

- [ ] Đổi schema hoặc response: đã cập nhật `docs/decisions/` và tài liệu trong cùng PR
- [ ] Mã lỗi, HTTP status khớp bảng D05; lỗi 500 không lộ stacktrace hay đường dẫn
- [ ] API không resize hoặc nén ảnh; giải mã đúng một lần, `score()` gọi chuẩn hóa đúng một lần
- [ ] Đầu vào không hợp lệ không gọi model (số lần gọi model = 0)

</details>

<details>
<summary><b>Dữ liệu / ML (data/, models/, scripts/)</b></summary>

- [ ] Đổi tham số chuẩn hóa thì đã tăng `NORMALIZATION_VERSION` và nêu việc phải trích lại đặc trưng, train lại
- [ ] Việc ghi đè dữ liệu có baseline `data/processed_baseline.sha256` chụp **trước** khi ghi
- [ ] Split không rò rỉ (không trùng ảnh giữa train, val, test); không tune trên test
- [ ] Số liệu báo **theo từng source**, kèm N, không chỉ số tổng; nói rõ val hay test
- [ ] Có lệnh tái lập, commit, `dirty=false`, seed; báo cáo không chứa đường dẫn máy cá nhân
- [ ] Nêu rủi ro shortcut (dung lượng file, dấu vết JPEG, metadata) nếu có số liệu mới

</details>

<details>
<summary><b>Test (tests/, locust/)</b></summary>

- [ ] Test kiểm hành vi theo hợp đồng, không chỉ lặp lại cài đặt; không `skip`, `xfail` hay `assert True` thiếu lý do
- [ ] Sửa lỗi: có test fail trước khi sửa và pass sau khi sửa
- [ ] Test chạy độc lập thứ tự, không cần mạng, GPU hay model thật (trừ test gắn marker riêng)

</details>

<details>
<summary><b>Docs / Spec (docs/, specs/, .specify/)</b></summary>

- [ ] Quyết định mới ghi rõ trạng thái `proposed` hay `approved` và người duyệt
- [ ] Không còn `[CẦN CHỐT]` mâu thuẫn với quyết định đã duyệt; liên kết nội bộ không vỡ

</details>

## Checklist chung

<!-- Chỉ tick khi đã làm thật. Không áp dụng thì ghi N/A và lý do, đừng tick. -->
- [ ] Nhánh đặt tên `ten/mo-ta-ngan`; commit tiếng Anh có tiền tố (`feat:`, `fix:`, `docs:`, `chore:`, `test:`)
- [ ] Một PR một mục đích; nếu làm thay phần của người khác thì đã ghi rõ và gắn người đó review
- [ ] Đổi cách dùng một thư mục thì đã cập nhật `README.md` của thư mục đó
- [ ] Không commit dữ liệu, model nặng, secret (`.env`), đường dẫn tuyệt đối máy cá nhân
