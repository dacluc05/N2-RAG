# FinSight Intelligence V2

Hệ thống Multi-Tool RAG và Multi-Agent để nghiên cứu doanh nghiệp niêm yết Mỹ. Báo cáo có tám nhóm phân tích, dữ liệu tài chính từ SEC, các phép tính Python và trình kiểm tra nhận định theo bằng chứng. Báo cáo công khai phần dữ liệu thiếu, mâu thuẫn và trạng thái từng agent.

## Chạy trên Windows

Mở thư mục `03-finsight-intelligence-v2` trong VS Code hoặc Antigravity. Dùng Windows x64, Python 3.12 x64 và MySQL 8 đã khởi động. Cài đặt không cần Docker.

1. Trong PowerShell, chạy:

   ```powershell
   py -0p
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
   ```

2. Trong MySQL Workbench hoặc trình quản trị MySQL, đăng nhập bằng tài khoản có quyền tạo cơ sở dữ liệu và người dùng. Thay `MAT_KHAU_MOI` trước khi chạy. Nếu tài khoản đã tồn tại, dùng mật khẩu của tài khoản đó trong `.env`.

   ```sql
   CREATE DATABASE IF NOT EXISTS finsight_intelligence
       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER IF NOT EXISTS 'finsight_user'@'localhost' IDENTIFIED BY 'MAT_KHAU_MOI';
   GRANT ALL PRIVILEGES ON finsight_intelligence.* TO 'finsight_user'@'localhost';
   ```

3. Điền `MYSQL_PASSWORD`, `SEC_USER_AGENT`, `GEMINI_API_KEY`, `GEMINI_MODEL` và `BRAVE_SEARCH_API_KEY` trong `.env`. User-Agent SEC có dạng tên ứng dụng kèm email liên hệ thật. Chọn model Gemini hỗ trợ structured output từ danh sách của tài khoản. Khi thiếu khóa Gemini, phần dữ liệu SEC và tính toán Python vẫn hoạt động với trạng thái có giới hạn.

   - `SEARCH_PROVIDER=off` tắt tìm kiếm web. Chế độ chuyên sâu sử dụng cả Brave Web Search và LLM Context nếu được cấu hình.
   - `ALLOWED_SOURCE_HOSTS=["ir.example.com"]` giới hạn máy chủ có thể tải ngoài SEC. Chỉ thêm máy chủ vào `PERSIST_SOURCE_HOSTS` nếu bạn có quyền lưu và gửi đoạn trích cho nhà cung cấp AI. Cấu hình mặc định dùng hồ sơ SEC để làm bằng chứng.
   - `PERSIST_MARKET=false` giữ Yahoo ngoài dữ liệu báo cáo và các hệ số phụ thuộc vốn hóa. Chỉ bật khi có quyền lưu và sử dụng các dữ liệu dẫn xuất.

Trong báo cáo, mục **Báo chí và mạng xã hội** dùng Brave Web Search để tra cứu theo mã doanh nghiệp khi bạn bấm tìm. Kết quả tra cứu tại chỗ chỉ gồm tiêu đề và liên kết, có thể mới hơn mốc chốt dữ liệu của báo cáo. Nếu cần đưa bài báo vào bằng chứng cho phiên nghiên cứu mới, cấu hình tên miền tương ứng trong cả `ALLOWED_SOURCE_HOSTS` và `PERSIST_SOURCE_HOSTS`. Bài đăng mạng xã hội phục vụ theo dõi thảo luận cộng đồng.

Agent **Lead** tổng hợp các nhận định đã kiểm chứng thành các đoạn đánh giá có dẫn chứng. Mở **Tổng quan** hoặc **Nhóm phân tích → Lead · Tổng hợp** trong báo cáo mới để xem kết quả.

Sau khi cập nhật, chạy `python -m alembic upgrade head` bằng môi trường ảo của dự án để tạo kho dùng chung SEC. FinSight kiểm tra danh sách hồ sơ theo mỗi phiên. Hồ sơ đã tách đoạn được dùng lại theo accession, URL và cấu hình tách đoạn. Company Facts được dùng lại tối đa một giờ nếu danh sách accession tài chính tương ứng giữ nguyên. **Trung tâm bằng chứng** hiển thị số hồ sơ tải mới và dùng lại.

Khi phân tích, có thể nhập giá USD, ngày và URL nguồn trong **Giá tham chiếu có nguồn**. Với `PERSIST_MARKET=true`, phiên phân tích tại ngày hiện tại có thể lấy giá đóng cửa Yahoo tự động. Vốn hóa ước tính dùng số cổ phiếu SEC đã công bố tại ngày giá. Bội số dùng số liệu năm tài chính gần nhất. Khi ô mã đối chiếu để trống, nhóm bán dẫn SIC 3674 dùng danh sách AMD, AVGO và NVDA sau khi kiểm tra lại mã ngành và bỏ mã đang phân tích.
   - MiniLM được tải ở lần đầu truy xuất dense. Có thể đặt `EMBEDDING_MODEL` thành thư mục model cục bộ. Đặt `EMBEDDING_ENABLED=false` để chạy BM25 khi thiếu model hoặc cần chạy nhẹ.

4. Áp dụng migration, chẩn đoán và khởi động:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m scripts.doctor
   .\.venv\Scripts\python.exe -m scripts.doctor --live
   .\START_WINDOWS.bat
   ```

   Nếu đang chạy bản trước, dừng bằng Ctrl+C và chạy lại lệnh khởi động. Tiếp tục dùng tệp `.env` và cơ sở dữ liệu hiện tại. Bản dựng React đã đi kèm gói phát hành. Khi chỉnh mã frontend, dùng Node.js 22.12+ hoặc 24 LTS rồi chạy `BUILD_WEB_WINDOWS.bat`. Để mở Streamlit dự phòng, dùng `START_WINDOWS.bat --legacy`.

   `--live` có thể dùng quota. Mở [giao diện](http://127.0.0.1:8501) hoặc [API Swagger](http://127.0.0.1:8000/docs).

## Trình diễn và kiểm thử

- Phân tích `AAPL`, chọn mốc `2024-11-04` để minh họa một báo cáo lịch sử. Chọn ngày hiện tại để cho phép tìm kiếm live và dữ liệu thị trường. Tài liệu xem theo thời điểm được giới hạn theo ngày công bố.
- Trong **Tổng quan**, bấm **Xem bằng chứng** dưới từng điểm nổi bật hoặc kết luận. Trong **Tài chính**, chọn kỳ và mở **Công thức và số liệu đầu vào** để đối chiếu từng chỉ tiêu.
- Trong **Bằng chứng**, chọn một nhận định để xem trạng thái, đoạn trích, kỳ, công thức, nguồn và kiểm tra URL. Dùng **Mở và tô sáng đoạn gốc** cho trích đoạn HTML trên trình duyệt hỗ trợ Text Fragments (Chrome hoặc Edge). Dòng XBRL được định vị theo concept, kỳ, đơn vị và giá trị khi SEC có neo phù hợp. PDF mở đúng trang nếu đã lưu số trang. Đoạn lưu trong ứng dụng vẫn có tô sáng để đối chiếu khi trang gốc thay đổi hoặc trình duyệt không hỗ trợ. Trong **Lịch sử báo cáo**, có thể lọc, so sánh và chạy lại cùng tham số.
- Định giá DCF dùng FCFF và giả định do người dùng nhập, kèm bảng độ nhạy. Các hệ số thị trường trong báo cáo dùng vốn hóa cùng ngày chạy và kết quả năm gần nhất.
- Kiểm thử offline và benchmark:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m scripts.evaluate
  ```

Để chạy vòng lặp tích hợp MySQL, cấu hình riêng cơ sở dữ liệu có hậu tố `_test`, chạy Alembic trên cơ sở dữ liệu đó rồi đặt `$env:FINSIGHT_MYSQL_TEST='1'` và chạy `python -m pytest -m mysql -q`. Luồng kiểm thử dùng SEC/Gemini mô phỏng, ghi rồi xóa bản ghi của lần kiểm thử trong cơ sở dữ liệu thử.

## Xử lý lỗi thường gặp

| Triệu chứng | Việc cần kiểm tra |
|---|---|
| Không tìm thấy Python | `py -0p` phải liệt kê 3.12 x64. |
| MySQL chưa sẵn sàng | Xem dịch vụ MySQL trong Services, kiểm tra host, port, mật khẩu, database và chạy Alembic. |
| Gemini 401/403/404 | Xác minh khóa, quyền model và tên model trong Google AI Studio. Chạy `scripts.doctor --live`. |
| Brave 429 | Kiểm tra quota gói, giảm ngân sách và tốc độ. DDGS chỉ được dùng nếu bật tùy chọn. |
| SEC 403 | Kiểm tra email nhận diện, chính sách mạng và khả năng truy cập SEC. |
| Trùng cổng | Sửa `BACKEND_PORT` và `FRONTEND_PORT` trong `.env`, rồi chạy lại. |
| PDF thiếu font | Đặt `PDF_FONT_PATH` là đường dẫn font TTF hỗ trợ tiếng Việt. Windows mặc định dùng Arial. |

Xem [đối chiếu Original → V1 → V2](docs/ORIGINAL_V1_V2.md), [kiến trúc và vận hành](docs/ARCHITECTURE.md), [phương pháp kiểm chứng](docs/VERIFICATION.md) và [đánh giá](docs/EVALUATION.md).

## Giao diện FinSight 2.1

- [Kiến trúc, hướng dẫn sử dụng và tệp thay đổi](docs/GIAO_DIEN_2_1.md)
- [Kết quả kiểm thử](docs/KIEM_THU_2_1.md)
