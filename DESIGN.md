---
version: alpha
name: "Bike Rental"
description: "Không gian phân tích nhu cầu thuê xe theo giờ, trực quan, với HistGradientBoosting làm mô hình dự đoán chính của bản demo."
colors:
  primary: "#0878B6"
  navy: "#10243B"
  ink: "#19324C"
  muted: "#586E83"
  cyan: "#69D8EF"
  background: "#F3F7FB"
  surface: "#FFFFFF"
  border: "#DCE6EE"
  soft-blue: "#EAF5FD"
  amber: "#E9B765"
  success: "#176746"
  danger: "#A32D24"
typography:
  sans:
    fontFamily: "Segoe UI, Arial, sans-serif"
  display:
    fontFamily: "Bahnschrift, Segoe UI, Arial, sans-serif"
rounded:
  DEFAULT: "16px"
  sm: "9px"
  md: "12px"
  lg: "16px"
spacing:
  section-gap: "22px"
  page-max: "1920px"
components:
  button:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.DEFAULT}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  navigation:
    backgroundColor: "{colors.navy}"
    textColor: "#C5D4E2"
  navigation-active-indicator:
    backgroundColor: "{colors.cyan}"
  secondary-surface:
    backgroundColor: "{colors.soft-blue}"
    textColor: "{colors.ink}"
  divider:
    backgroundColor: "{colors.border}"
  help-text:
    textColor: "{colors.muted}"
  overview-chart:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.surface}"
  overview-peak:
    backgroundColor: "{colors.amber}"
  status-success:
    textColor: "{colors.success}"
  status-error:
    textColor: "{colors.danger}"
---

# Bike Rental Design System

## Overview

Website tiếng Việt giúp người học và người sử dụng quan sát nhu cầu thuê xe Capital Bikeshare theo giờ. Bối cảnh là dữ liệu Washington, D.C. năm 2011–2012. Đây là công cụ phân tích và mô phỏng, không phải màn hình theo dõi hoạt động trực tiếp. Nguồn nghiệp vụ: website/app.py, website/history.py và website/models/provenance.json; yêu cầu của người dùng ngày 02/11/2026 là giao diện thiên về công nghệ, trực quan và giữ nguyên mô hình.

Ý tưởng thị giác là bàn phân tích nhịp thuê xe trong một ngày: thanh điều hướng tối, vùng dữ liệu sáng và histogram 24 giờ làm điểm nhận diện. Tông xanh–trắng và menu bên trái tiếp tục được giữ. Không dùng nền neon, hiệu ứng phát sáng hoặc số liệu giả để tạo cảm giác công nghệ.

Runtime CSS trong website/static/style.css là nguồn token chuẩn (Model B). Tài liệu này phản ánh giá trị CSS và lý do sử dụng; không có bước sinh token tự động. UX-CONTRACT.md sở hữu luồng tương tác.

## Colors

Primary là xanh cho thao tác và đường dự đoán. Navy dành cho menu, khối kết quả và biểu đồ tổng quan. Cyan nhấn số dự đoán trên nền navy. Amber đánh dấu đỉnh 17h trong histogram lịch sử; chữ mô tả giải thích đỉnh bằng văn bản. Màu success chỉ dùng cho trạng thái sẵn sàng; danger đi cùng thông báo lỗi. Border và background tách vùng mà không cần nhiều đổ bóng.

Bản đồ nhiệt giữ dải chuyển màu pastel xanh–lục–vàng–cam–đỏ; các token --heat-0 đến --heat-4 tiếp tục được history.js dùng để nội suy. Phần đối chiếu giữ hai nét xanh liền và cam đứt để phân biệt cả khi không dựa vào màu. Chỉ hỗ trợ giao diện sáng; forced-colors ưu tiên màu hệ thống và viền nhận diện.

## Typography

Body dùng Segoe UI có dấu tiếng Việt, fallback Arial. H1 và số nổi bật dùng Bahnschrift, fallback Segoe UI. Không tải font từ mạng. Nội dung hướng dẫn và bảng dùng cỡ 16px; nhãn phụ 12–15px. H1 28–51px tùy bề rộng. Chữ đậm và kích thước thể hiện thứ bậc, không dùng toàn bộ trang chữ hoa. Các giá trị thuê xe dùng tabular-nums và Intl.NumberFormat('vi-VN').

## Layout

Menu cố định, mặc định 244px ở desktop, có thể ẩn và đổi độ rộng bằng kéo hoặc bàn phím. Giá trị người dùng đã lưu được giữ lại. Nội dung cuộn theo tài liệu; không khóa chiều cao trang. Menu hẹp dùng icon kèm nhãn ngắn xếp dọc. Trang chủ gồm lời giới thiệu, histogram lịch sử, phạm vi dữ liệu và các lối vào chức năng.

Biểu mẫu desktop chia hai cột thời điểm/thời tiết; dưới là số dự đoán và biểu đồ 24 giờ. Ở màn hình vừa, biểu mẫu và kết quả xếp cạnh nhau hoặc một cột khi không còn đủ chỗ. Ở mobile, menu được giới hạn 84–96px để không chiếm chỗ của nội dung; các trường và thẻ số liệu xếp một cột. Bảng và biểu đồ rộng cuộn trong chính vùng của chúng. Bảng slot tối đa 10 dòng mỗi trang, cao tối đa 430px; biểu đồ tối thiểu 460px và heatmap 760px để chữ không bị ép nhỏ.

## Elevation & Depth

Các khối dữ liệu dùng viền 1px, nền sáng và khoảng cách 22px. Không dùng backdrop blur hoặc bóng cho toàn bộ card. Hover nút và lối vào chức năng có bóng nhẹ; tooltip có bóng để tách khỏi dữ liệu bên dưới. Hệ thống trạng thái không làm thay đổi chiều rộng nút khi đang tính.

## Shapes

Card chính bo 16px; vùng phụ 12px; input và nút bo 9px. Icon SVG nét 1.65–1.7px, khung 20–24px. Nhãn luôn đi cùng icon điều hướng. Histogram dùng cột bo đỉnh 3px; ô heatmap bo 4px để khoảng trống giữa các giờ vẫn rõ.

## Components

| Vai trò trong tài liệu               | Token CSS chuẩn                             | Thành phần dùng                |
| ------------------------------------ | ------------------------------------------- | ------------------------------ |
| colors.primary                       | --green (tên tương thích cũ), --water alias | Nút chính, link, đường dự đoán |
| colors.navy                          | --navy, --deep-water alias                  | Menu, kết quả, histogram       |
| colors.ink / muted                   | --ink / --muted                             | Nhãn, hướng dẫn, bảng          |
| colors.cyan                          | --cyan, --lime alias                        | Kết quả trên nền tối           |
| colors.background / surface / border | --bg / --white / --line                     | Bố cục và viền                 |
| colors.soft-blue / amber             | --soft-blue / --amber                       | Vùng phụ, đỉnh histogram       |
| colors.success / danger              | --success / --danger                        | Trạng thái và lỗi              |
| typography.sans / display            | --font-body / --font-display, --font-data   | Nội dung, tiêu đề và số        |
| rounded.DEFAULT / sm                 | --radius / --radius-control                 | Card và điều khiển             |

Input ngày và select tiếp tục do trình duyệt sở hữu popup, đúng UX-CONTRACT.md. validateForm là chủ sở hữu kiểm tra trường dùng chung. Nút gửi bị khóa khi đang tính. Lỗi có văn bản cạnh trường, aria-invalid và focus lỗi đầu. Các vùng status dùng live region; trạng thái cũ không được gắn nhãn như kết quả mới sau khi sửa đầu vào.

navigation.js chỉ quản lý đường dẫn hash, tiêu đề trang, phần giới thiệu và hình thức thanh bên. Các icon là SVG nội bộ có aria-hidden và nhãn chữ. Không gọi mô hình từ mã điều hướng. Thanh xếp hạng ở trang giờ cao điểm lấy tỷ lệ giữa ba kết quả đã trả về; không thay đổi số dự đoán hoặc ý nghĩa thống kê.

Các biểu đồ giữ tooltip khi chạm đúng đường/điểm, có bảng số liệu thay thế. Heatmap giữ bàn phím và drill-down theo từng ô. Phạm vi 17.379 bản ghi và 731 ngày trên trang chủ lấy từ data/raw/hour.csv; cập nhật các số và histogram nếu thay nguồn dữ liệu. Nhãn trạng thái và chú thích luôn phân biệt lịch sử với dự đoán.

Hover/focus của nút và link dùng thời lượng 160ms. Không có chuyển động trang trí hoặc số liệu nhấp nháy. prefers-reduced-motion tắt chuyển động. Scrollbar có màu, trạng thái hover và fallback WebKit; forced-colors dùng mặc định hệ thống.

## Do's and Don'ts

- Giữ một thao tác chính cho mỗi màn hình và hiển thị rõ nguồn của số liệu.
- Giữ nguyên model.joblib, API và dữ liệu huấn luyện trong các lần chỉnh giao diện.
- Không diễn giải R² thành phần trăm chắc chắn cho một dự đoán.
- Phần dự đoán và đối chiếu hiển thị tên mô hình đang chạy; phần đánh giá mặc định chọn cùng mô hình đó.
- Không dùng icon không nhãn, số liệu mô phỏng như thể là thực tế, hoặc hiệu ứng làm khó đọc biểu đồ.

Thay đổi có chủ đích so với bản trước: tiêu đề Georgia chuyển sang Bahnschrift/Segoe UI và kết quả xanh nhạt chuyển thành navy với số cyan theo yêu cầu đổi phong cách. Các token dùng chung được gom về một khối :root thay cho nhiều lần ghi đè trong CSS.
