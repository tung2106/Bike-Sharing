# Bike Rental — Dự báo lượt thuê xe đạp theo giờ

Bike Rental ước lượng số lượt thuê xe đạp theo giờ từ thông tin lịch và thời tiết của hệ thống Capital Bikeshare. Website dùng **HistGradientBoosting (HGB) 400 vòng** để dự đoán. Kết quả của các mô hình **Random Forest** được hiển thị trong mục **Đánh giá mô hình** để đối chứng.

## Chạy trên Windows

Cần Git và Python 3.12 hoặc 3.13. Chạy các lệnh sau trong PowerShell khi cài lần đầu.

```powershell
git clone --branch main --single-branch https://github.com/tung2106/Bike-Sharing.git
cd Bike-Sharing
.\website\setup.ps1
```

Nhấp đúp [scripts/MO_WEBSITE.cmd](scripts/MO_WEBSITE.cmd) hoặc chạy `.\website\start.ps1` từ thư mục gốc. Giữ cửa sổ máy chủ mở khi sử dụng. Website chạy tại [http://127.0.0.1:8002/](http://127.0.0.1:8002/).

Trong **Dự đoán theo giờ**, thử ngày **13/09/2012** lúc **08:00**, thời tiết quang đãng, nhiệt độ **22 °C**, nhiệt độ cảm nhận **23 °C**, độ ẩm **65%**, gió **10 km/h** và bỏ chọn ngày lễ. Web hiển thị **717 lượt** cho giờ đã chọn, kèm biểu đồ 24 giờ. Mục **Giờ cao điểm** xếp ba khung giờ theo số lượt ước lượng.

Mục **Khám phá lịch sử** trình bày bản đồ nhiệt theo thứ và giờ. Mục **Đối chiếu thực tế** cho phép chọn ngày trong tập kiểm tra để đọc số lượt quan sát và dự đoán của HGB theo giờ.

## Dữ liệu và thực nghiệm

Nguồn dữ liệu là [Bike Sharing của UCI](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset), thu thập tại Washington, D.C. từ năm 2011 đến 2012. [hour.csv](data/raw/hour.csv) có **17.379 bản ghi giờ**, dùng cho HGB. [day.csv](data/raw/day.csv) có **731 bản ghi ngày**, dùng để tạo đặc trưng tổng lượt thuê ngày trước cho một bản Random Forest đối chứng.

Nhóm thử 100, 200, 300, 400 và 600 vòng trên ba đợt kiểm định theo thời gian. Mốc 400 có MAE gộp thấp nhất trong các mốc đã thử. Sau khi chọn cấu hình, nhóm huấn luyện lại HGB trên **14.771 bản ghi đầu** và đánh giá trên **2.608 bản ghi cuối**.

| Mô hình | MAE (lượt/giờ) | RMSE (lượt/giờ) | R² |
| --- | ---: | ---: | ---: |
| **HGB 85% · 400 vòng** | **40,58** | **63,79** | **0,9121** |
| Random Forest 85% | 54,67 | 82,07 | 0,8544 |
| Random Forest 85% + lượt thuê ngày trước | 53,10 | 81,03 | 0,8581 |
| Random Forest 70% | 61,36 | 90,16 | 0,8243 |

Các chỉ số được tính trên cùng tập kiểm tra lịch sử với thời tiết quan sát. Bản demo dùng một bộ điều kiện thời tiết cho cả 24 giờ của ngày tham chiếu. Để đánh giá ở một khu vực khác, cần dữ liệu của khu vực đó và thông tin thời tiết sẵn có tại thời điểm dự báo.

## Mã nguồn và báo cáo

| Đường dẫn | Nội dung |
| --- | --- |
| [website/](website/) | Ứng dụng Flask, giao diện và kiểm thử |
| [experiments/hourly_comparison/](experiments/hourly_comparison/) | Huấn luyện HGB cục bộ, gói mô hình và kết quả đánh giá |
| [docs/HUONG_DAN_THU_MUC.txt](docs/HUONG_DAN_THU_MUC.txt) | Cấu trúc dự án và các lệnh tái lập |
| [Báo cáo HGB — bản nộp](docs/reports/Bao_cao_Bike_Sharing_HGB_Ban_nop.docx) | Bản Word 67 trang, gồm bộ dữ liệu, lý thuyết và thực nghiệm |

Chạy từ thư mục gốc để kiểm tra website hoặc tái lập thí nghiệm chọn số vòng HGB. Lần huấn luyện mới lưu kết quả trong thư mục riêng dưới `experiments/hourly_comparison/runs/`.

```powershell
.\website\.venv\Scripts\python.exe -B -m unittest discover -s website/tests -p "test_*.py"
.\website\.venv\Scripts\python.exe -B experiments\hourly_comparison\train_hgb_rounds.py
```
