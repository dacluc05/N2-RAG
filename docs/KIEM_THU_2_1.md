# Báo cáo kiểm thử FinSight 2.1.0

## Môi trường

Windows, Python 3.12, Node 24, Chrome headless qua Playwright và MySQL đang dùng bởi dự án. Bản kiểm thử chạy ở cổng riêng. Dữ liệu giao diện lấy từ báo cáo AAPL và NVDA đã lưu.

## Kết quả

| Hạng mục | Kết quả |
| --- | --- |
| Kiểm tra kiểu TypeScript và bản dựng Vite | Thành công. Vite ghi cảnh báo chỉ thị thư viện client khi đóng gói. |
| Pytest | 34 đạt, 1 bỏ qua. Ca MySQL chuyên dụng yêu cầu cơ sở dữ liệu kiểm thử riêng. |
| Windows | Khởi động bằng `START_WINDOWS.bat`. API và máy chủ giao diện đều trả 2.1.0, MySQL sẵn sàng. |
| Dashboard và lịch sử | Đọc số liệu thật. Lọc tên Apple chỉ trả AAPL. |
| Báo cáo | Mở Apple, chuyển bảng tài chính năm/quý, đổi sang triệu USD, xem nhóm phân tích và lọc nhận định. |
| Bằng chứng số liệu | Nút của kết luận quý Apple trỏ tới neo SEC `#f-56`. |
| Bằng chứng văn bản | Ngăn tô sáng trích đoạn. Chrome mở HTML gốc NVIDIA đã lưu và cuộn tới đoạn được trích dẫn. |
| Xuất báo cáo | Trình duyệt tải JSON. API xuất PDF và Markdown thành công. |
| So sánh và DCF | Chọn hai báo cáo, xem bảng đối chiếu, chạy DCF và hiển thị bảng độ nhạy. |
| Tiến trình | Đọc được sự kiện tiến trình từ phiên đã lưu. |
| Kích thước màn hình | Kiểm tra 1920, 1440, 1366, 768 và 390 px. Kiểm tra điều hướng thu gọn trên điện thoại. |
| Chủ đề sáng/tối | Chuyển đổi thành công và đã lưu ảnh giao diện thực tế. |
| API cục bộ | Yêu cầu ghi từ nguồn ngoài bị từ chối với 403. Cấu hình giao diện chỉ trả giới hạn tìm kiếm. |
| Lượt gọi ngoài dự kiến | Luồng trình duyệt chỉ gửi một yêu cầu POST để tính DCF. Không tạo job phân tích khi xem báo cáo hay đổi chủ đề. |

Chưa chạy một phiên nghiên cứu mới qua Gemini và Brave trong lần kiểm thử này. Chưa kiểm tra thao tác xóa hoặc ghi phản hồi trên báo cáo thật. Phần xóa và phản hồi được kiểm tra bằng API với dữ liệu kiểm thử.

Ảnh trong `docs/screenshots` được chụp từ bản chạy thử.
