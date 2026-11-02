# Luồng sử dụng

Các mục trên thanh bên dùng đường dẫn hash. Khi chuyển mục, dữ liệu nhập vẫn được giữ lại. Khám phá lịch sử hiển thị lượt thuê đã ghi nhận. Đối chiếu thực tế đặt dự đoán cạnh quan sát cùng giờ.
Biểu mẫu kiểm tra ngày và thời tiết. Trong khi tính, khóa nút gửi. Nếu người dùng thay đầu vào, yêu cầu tính lại trước khi đọc kết quả mới. Giữ điều khiển ngày và danh sách chọn dùng được bằng bàn phím, chỉ báo focus, thông báo lỗi và bảng số liệu thay thế cho biểu đồ.

## Chi tiết bản đồ nhiệt

history.py sở hữu lọc lịch sử, cả bản đồ nhiệt và /api/history/slot cùng dùng select_history. dayofweek dùng Thứ Hai = 0. Một ngày thiếu bản ghi giờ không được thay bằng 0.
Khi bấm ô, history.js giữ focus trên nút, tải phần chi tiết ngay dưới bản đồ và đọc trạng thái bằng live region. Đổi ô hoặc sửa bộ lọc hủy yêu cầu trước, kết quả cũ không được hiển thị lại. Bảng chia 10 dòng mỗi trang, sắp theo ngày hoặc lượt thuê; nút thử lại chỉ xuất hiện khi yêu cầu lỗi.
Các bộ lọc lịch sử và ô chọn được giữ trong phiên trang đang mở; phù hợp điều hướng hash hiện tại. Native select/date giữ hành vi của trình duyệt. Chỉ phần chi tiết bảng cuộn nội bộ. Không có lưu hoặc sửa dữ liệu.

## Chủ sở hữu thành phần

| Capability     | Canonical owner           | Source of truth              | Allowed variants                 | Verification                            |
| -------------- | ------------------------- | ---------------------------- | -------------------------------- | --------------------------------------- |
| Select/Listbox | Native select             | index.html và history.js     | Sắp xếp bảng và bộ lọc           | Bàn phím, phân trang                    |
| Date           | Native date input         | index.html                   | Ngày mô phỏng và khoảng lịch sử  | Kiểm tra ngày tại API và biểu mẫu       |
| Form           | validateForm trong app.js | Ràng buộc input và API Flask | Dự đoán và lịch sử               | Lỗi hiển thị cạnh trường, focus lỗi đầu |
| Scrollbar      | style.css                 | DESIGN.md                    | Bảng có scrollbar-gutter ổn định | Màn hình hẹp                            |
| Toast          | Inline live status        | index.html và history.js     | Tải, lỗi, thử lại                | UI thành công và lỗi                    |

## Hiển thị dashboard

Thanh bên dùng SVG kèm nhãn chữ, vẫn có thể ẩn và thay đổi độ rộng bằng kéo hoặc bàn phím. navigation.js sở hữu tiêu đề và mô tả theo từng route; việc điều hướng không gửi yêu cầu dự đoán và giữ giá trị biểu mẫu. Thanh ở các thẻ giờ cao điểm chỉ biểu diễn tỷ lệ giữa ba dự đoán đã có. Phong cách và token dùng chung được ghi trong DESIGN.md và website/static/style.css.
