# streamlit/ – Giao diện demo

Phụ trách: Loan

## Làm gì
Kéo thả ảnh, hiện kết quả từ API. Hai trang: "Kiểm tra ảnh" và "Kết quả đánh giá".

## Cách chạy
`streamlit run streamlit/app.py`

## Input / Output
- Input: ảnh người dùng kéo thả.
- Output: verdict, điểm, lý do; bảng số đo đánh giá.

## Lưu ý và giả định
- Gọi API qua Nginx, không gọi thẳng model.
