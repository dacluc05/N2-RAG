# Kết quả đánh giá và kịch bản demo

## Kiểm thử thực hiện trên Windows

| Hạng mục | Kết quả |
|---|---|
| Bộ pytest V2 | 30 ca đạt, gồm một ca tích hợp MySQL thật với các dịch vụ nghiên cứu mô phỏng. |
| Python 3.12 x64 | Cài các phụ thuộc, `pip check`, compile và kiểm tra import. |
| MySQL Community Server 8.0.44 | Dùng một instance riêng. Alembic upgrade và kiểm tra khớp schema. Job mock chạy qua API, lưu báo cáo, đọc lại và xóa theo quan hệ. |
| FastAPI và Streamlit | Hai tiến trình khởi động trên loopback và phản hồi health. AppTest kiểm tra giao diện. |
| Xuất báo cáo | JSON, Markdown và PDF. Kiểm tra trích xuất Unicode tiếng Việt và liên kết trong PDF. |
| RAG | FAISS chạy với vector kiểm soát trong test. MiniLM chạy trực tiếp, sinh vector kích thước 384. |
| Yahoo Finance | Gọi trực tiếp AAPL. Kết quả kiểm tra có 36 quan sát giá, đơn vị USD và có trường vốn hóa. |
| Brave, Gemini và SEC | Kiểm thử API bằng phản hồi mô phỏng, gồm cả payload structured output do SDK Gemini tạo. Chưa chạy end-to-end qua cả ba dịch vụ bằng cấu hình live. SEC Form 10-K được kiểm tra trực tiếp làm nguồn tham chiếu cho benchmark. |
| Baseline V1 | 12 test có sẵn đạt. Quy tắc kiểm tra ID được chạy trực tiếp trong benchmark V2. |
| Baseline Original | Đọc PDF và commit gốc. Chưa chạy pipeline live với model và corpus chung. |

## Benchmark có đáp án

`benchmark-results.json` ghi đầu vào, đáp án, kết quả, đạt/trượt và thời gian của 10 ca. Chạy lại bằng `python -m scripts.evaluate`. Tùy chọn `--v1 <thư-mục-V1>` thực thi thêm hàm kiểm tra ID của V1 trên cùng câu thử nghiệm.

| Tiêu chí | Cách đo và phạm vi |
|---|---|
| Dữ liệu và phép tính | SEC Apple FY2024, so doanh thu đã công bố và công thức tính tăng trưởng, biên gộp, dòng tiền tự do. |
| Xử lý thiếu | ROIC trả null khi thiếu đầu vào. |
| Trích dẫn và mâu thuẫn | Câu 18% bị bác bỏ dù S1 tồn tại. Mã không tồn tại bị từ chối. |
| Phù hợp thời gian | Đoạn công bố sau ngày phân tích không xuất hiện khi truy xuất. Test riêng kiểm tra 10-K/A chỉ có hiệu lực từ ngày công bố. |
| Chất lượng truy xuất | Một truy vấn có đoạn liên quan gán nhãn. FAISS được kiểm tra bằng vector kiểm soát. Chưa đo Recall@K theo nhiều công ty. |
| Độ bao phủ và đầy đủ báo cáo | Integration kiểm tra report có trạng thái partial khi thiếu các chiều và không biến dữ liệu thiếu thành 0. |
| Latency và API usage | Thời gian benchmark cục bộ lưu trong JSON. Lượt gọi, token và thời gian của job đo trong ứng dụng. Chưa đo chi phí live trên nhiều công ty. |

Fixture số Apple trích từ [Form 10-K FY2024](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm), bảng kết quả hoạt động và bảng dòng tiền. Các tình huống trích dẫn sai, thiếu nguồn, sai kỳ, cùng CIK và hạn mức là mô phỏng gắn nhãn. Báo cáo benchmark đo năng lực trong các ca kiểm soát. Chưa có kết quả đối chứng đầu-cuối về chất lượng phân tích giữa Original, V1 và V2.

## Demo 6–8 phút

1. Mở trang **Tổng quan** và kiểm tra MySQL cùng cấu hình dịch vụ. Tra AAPL bằng ô tra cứu SEC. Xác nhận CIK 320193.
2. Phân tích mốc 04/11/2024. Xem tiến trình thu thập, truy xuất, phân tích và kiểm chứng. Với ngày hiện tại, chọn **Chuyên sâu** để bật cả hai chế độ Brave khi khóa có quyền.
3. Mở **Tài chính**. Chọn doanh thu FY2024 và mở hồ sơ nguồn. Giải thích vì sao chương trình so theo ngày kết thúc năm tài chính và loại bản công bố sau mốc.
4. Mở **Bằng chứng**. Chọn một nhận định, xem đoạn trích, ngày, kỳ và công thức. Chạy `python -m scripts.evaluate` để tái hiện câu 18% bị bác bỏ có kiểm soát. Báo cáo live có thể không xuất hiện nhận định sai.
5. Mở **Phân tích từng agent**. Giải thích trạng thái của các vai trò. Chọn **Lịch sử báo cáo** để chứng minh lần chạy còn lưu trong MySQL và xuất báo cáo PDF.
6. Kết thúc với bảng đối chiếu Original → V1 → V2. Trình bày riêng kết quả kiểm thử có đo, phần dùng API mock và phần chưa có baseline đầu-cuối.
