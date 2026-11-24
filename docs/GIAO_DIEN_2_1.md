# Kiến trúc giao diện FinSight 2.1

## Luồng sử dụng

- **Tổng quan** mở nhanh báo cáo gần nhất, tra cứu mã hoặc tên doanh nghiệp, theo dõi số báo cáo, nhận định và bằng chứng đã lưu.
- **Phân tích doanh nghiệp** tra cứu SEC, đặt mốc dữ liệu, chọn phạm vi, ngân sách tìm kiếm và xem các sự kiện tiến trình do API trả về.
- **Hồ sơ doanh nghiệp** gồm tổng quan, tài chính, chủ đề, định giá, nhóm phân tích, bằng chứng và xuất báo cáo. Các chủ đề dùng tám khía cạnh do pipeline cung cấp.
- **Bằng chứng** mở trong ngăn bên phải, giữ vị trí đọc và cho phép đóng bằng Escape. Trích dẫn dùng ID từ báo cáo đã lưu. Đoạn trích nguyên văn giữ ngôn ngữ nguồn.
- **Tài chính** hiển thị kỳ năm hoặc quý, đơn vị USD đến tỷ USD cho biểu đồ và giải thích đầu vào bằng tiếng Việt. Thiếu số liệu hiển thị dấu gạch ngang hoặc thông báo.
- **So sánh** đọc 2–4 phiên đã lưu. Biểu đồ chỉ xuất hiện khi có đủ số liệu USD và kỳ năm tài chính nằm trong khoảng 92 ngày. Cột số liệu giữ ngày kết thúc kỳ riêng.
- **Lịch sử** tìm theo tên hoặc mã, ngày, trạng thái, có phân trang ở API. Tên và ngành đến từ hồ sơ đã lưu.
- **Định giá DCF** gửi các giả định người dùng nhập sang công thức DCF hiện có.

## Thành phần và dữ liệu

Trình duyệt tải React, TypeScript và CSS từ máy chủ cục bộ tại cổng giao diện. Vite tạo bản dựng, React Router điều hướng, TanStack Query quản lý truy vấn và Recharts vẽ biểu đồ. Các trang báo cáo, so sánh, định giá và biểu đồ tài chính được tải theo nhu cầu. Màu giao diện sáng hoặc tối được lưu trong trình duyệt.

Máy chủ giao diện chuyển tiếp các yêu cầu được phép tới FastAPI. Token nội bộ, nếu cấu hình, chỉ được gắn khi chuyển tiếp phía máy chủ. Yêu cầu ghi phải xuất phát từ giao diện cùng nguồn. Máy chủ giao diện chỉ lắng nghe trên máy cục bộ. Khóa Gemini, Brave và kết nối MySQL ở phía Python.

FastAPI, MySQL và pipeline vẫn cung cấp số liệu gốc. Giao diện dùng lại phép tính tóm tắt kỳ của Python. Thống kê mở rộng đọc bảng đã có. Bản này không cần migration mới.

## Bằng chứng và giới hạn dữ liệu

- **Nguồn đối chứng** mở tài liệu HTML tại đoạn trích bằng Text Fragment. Nút **Đọc đoạn trích** mở bản nguyên văn đã lưu.
- Với XBRL, **Nguồn đối chứng** mở hàng nguyên văn trong FinSight và đánh dấu ô đã đối chiếu theo chỉ tiêu, kỳ, đơn vị và giá trị. Liên kết tới SEC.gov có neo của ô và thêm Text Fragment cho lần xuất hiện đã xác định, dùng ngữ cảnh trong hồ sơ khi số liệu bị lặp.
- Với PDF có số trang, **Nguồn đối chứng** mở bản sao trang gốc đã đánh dấu đoạn trích nếu đối chiếu được một vị trí duy nhất. **Mở PDF gốc** mở trực tiếp tài liệu tại trang tương ứng.
- Khi chỉ xác định được URL, nút mở tài liệu và ghi rõ giới hạn định vị.
- Tiến trình dùng các sự kiện thực có sẵn trong pipeline. Chưa có bộ đếm nguồn, tài liệu hoặc nhóm phân tích theo từng bước trong thời gian thực.
- Bảng rủi ro, lợi thế cạnh tranh và nhóm phân tích dùng các nhận định đã lưu. Không tự gán điểm, xác suất hay đồng thuận khi báo cáo thiếu dữ liệu tương ứng.

## Tệp thay đổi

| Tệp | Nội dung |
| --- | --- |
| `frontend/web/src/App.tsx`, `Workspace.tsx` | Điều hướng, dashboard, tạo phiên, lịch sử và trạng thái |
| `frontend/web/src/Report.tsx`, `Finding.tsx`, `Evidence.tsx`, `Explorer.tsx` | Hồ sơ, nhận định, ngăn bằng chứng và bộ lọc |
| `frontend/web/src/Finance.tsx`, `Compare.tsx`, `Valuation.tsx` | Số liệu, biểu đồ, so sánh và DCF |
| `frontend/web/src/data.ts`, `ui.tsx`, `main.tsx`, `style.css` | Kiểu dữ liệu, API, thành phần và giao diện sáng/tối |
| `frontend/web/index.html`, `package.json`, `package-lock.json`, `tsconfig.json`, `.gitignore`, `THIRD_PARTY_LICENSES.txt`, `dist/` | Cấu hình frontend và bản dựng đi kèm ZIP |
| `scripts/web_ui.py`, `scripts/launch.py`, `scripts/setup_windows.ps1`, `START_WINDOWS.bat`, `BUILD_WEB_WINDOWS.bat` | Máy chủ giao diện, cài đặt và khởi chạy Windows |
| `finsight/api.py`, `storage.py`, `__init__.py` | API tóm tắt, lọc lịch sử, thống kê và phiên bản |
| `tests/test_integration.py` | Kiểm tra API mở rộng |
| `README.md`, `docs/GIAO_DIEN_2_1.md`, `docs/KIEM_THU_2_1.md` | Hướng dẫn, kiến trúc và kết quả kiểm thử |

Giao diện Streamlit vẫn có thể chạy bằng `START_WINDOWS.bat --legacy`.

## Kiểm chứng nhận định theo kỳ

- Tỷ số quý riêng dùng doanh thu và chỉ tiêu của cùng ngày bắt đầu, ngày kết thúc và tiền tệ. Số lũy kế không đi vào phép tính quý.
- Nhận định so sánh tỷ lệ cần có chỉ số và kỳ cho từng vế. Giá trị USD dùng số tuyệt đối. Đối chiếu số liệu thành công vẫn cần đánh giá nội dung nguồn trước khi kết luận.
- Phân tích theo chủ đề chỉ hiển thị nhận định đã xác minh. Các nhận định còn lại có thể tra soát tại Trung tâm bằng chứng.
- Kết quả kiểm chứng trong các báo cáo đã lưu được giữ theo lần chạy. Chạy phân tích lại để áp dụng bộ kiểm chứng mới.
