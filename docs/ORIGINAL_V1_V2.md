# Đối chiếu Original → V1 → V2

## Tư liệu rà soát

- PDF bốn trang `Topic 5 - RAG Agent.pdf`, bản in bài hướng dẫn của Erik Taylor ngày 17/07/2025. Trang 1–2 mô tả Multi-Tool RAG, nhóm vai trò và chiến lược tìm kiếm. Trang 3 trình bày một ví dụ NVIDIA. Trang 4 là thông tin xuất bản. Bài viết không cung cấp bộ ground truth hoặc benchmark định lượng.
- Repo `eriktaylor/ai-agent-moat`, commit `a5e33e7bc2d094ba53b7671f65b3811185ceca33`. Xem ứng dụng Streamlit, notebook, các biến thể ResearchAgent, bộ công cụ và hiển thị.
- V1 `FinSight-RAG-Complete.zip`. Rà soát sáu module trong `core/`, giao diện `app.py`, schema SQL, script Windows, cấu hình, tài liệu và bốn tệp kiểm thử. Bộ test V1 chạy độc lập có 12 ca đạt.
- Master Prompt `Pasted text(1).txt`, 1.610 dòng. Tên thư mục ưu tiên theo yêu cầu trực tiếp của phiên làm việc.

## Quyết định thiết kế

| Hạng mục | Original | V1 | V2 |
|---|---|---|---|
| Truy xuất đa công cụ | Colab kết hợp Google CSE, Yahoo và đọc PDF. Bản Streamlit dùng DDG và có ba truy vấn theo tầng trong ResearchAgent. | DDGS hoặc Google CSE, Yahoo và tải HTML/PDF. Có theo dõi nguồn, lỗi và ngân sách tải. | Kế thừa ý tưởng truy xuất theo tầng. SEC XBRL, hồ sơ SEC, Brave Web/Context, Yahoo và DDGS tùy chọn. Chia sáu nhóm truy vấn và có ngân sách từng tầng. |
| Dữ liệu tài chính | `get_stock_info` trả chuỗi dữ liệu Yahoo. Bản Streamlit có fallback từ lịch sử khi thiếu giá. | `core/finance.py` chuẩn hóa giá trị thiếu, lịch sử và kiểu khóa Yahoo. | Kế thừa nguyên tắc null có chủ đích. SEC là nguồn báo cáo, mốc công bố và accession được giữ. Yahoo bổ sung thị trường. Công thức trong `finsight/financials.py`. |
| RAG | FAISS theo context, tài liệu DDG có thể là cả cụm kết quả. `_create_rag_chain` dựng vector store cho từng lượt agent. | Chia đoạn và tạo một FAISS cho mỗi lần chạy. Metadata trích dẫn gắn theo nguồn. | Kế thừa MiniLM, FAISS và một index theo phiên. Thêm BM25, rank fusion, lọc CIK và ngày công bố. Hash, locator, ngày và ID đoạn ổn định trong cùng tài liệu. |
| Đa agent | Market Investor, Value Investor, Devil’s Advocate, Lead Analyst. | Giữ bốn vai trò và rubric chọn nhận định tổng hợp tiếng Việt. | Chia thành Thị trường, Tài chính, Mô hình và lợi thế, Rủi ro, Kiểm chứng, Tổng hợp. Có vòng phản biện giới hạn và schema Pydantic. |
| Trích dẫn | Đánh số theo lượt truy xuất, có thể lặp ID giữa các agent. | ID nguồn ổn định trong phiên. `validate_citations` đối chiếu ID được cho phép. | Đối chiếu CIK, ngày, đoạn trích, số liệu, đơn vị và kỳ. Agent kiểm chứng đánh giá mức hỗ trợ nội dung. Tổng hợp chỉ nhận claim SUPPORTED. |
| Nguồn không khả dụng | Xử lý lỗi theo nguồn. Bản web có `scrape_website` trả thông báo chưa triển khai. | Có fetch thật, đánh dấu snippet, chặn URL nội bộ dạng IP hiển nhiên. Kiểm tra tên miền chưa phân giải DNS. | DNS phải công khai, danh sách host cụ thể, HTTPS, không redirect, giới hạn byte và timeout. Brave chỉ khám phá URL. |
| Cơ sở dữ liệu | Bộ nhớ/cache theo phiên. | Sáu bảng MySQL, dùng ORM `create_all` và schema SQL riêng. | MySQL, migration Alembic, khóa idempotency trong thời gian job đang chạy, ghi báo cáo và liên kết bằng chứng trong một transaction. |
| Kết luận | Bullish, Bearish hoặc Neutral with Caution. | Ba mức nhận định và rubric. | Tám chiều phân tích và trạng thái thiếu bằng chứng. Đối chiếu doanh nghiệp chọn thủ công, định giá theo giả định và truy nguyên dữ liệu. |

V2 kế thừa phương pháp, vai trò, cách hiển thị tiến trình, nguyên tắc giữ giá trị thiếu và nhóm công nghệ phù hợp. Toàn bộ module V2 được viết riêng, có schema và kiểm thử tương ứng. Original và V1 chỉ được đọc hoặc chạy kiểm thử trên bản sao dùng để rà soát.

## Minh chứng định lượng có phạm vi

Dùng cùng một mệnh đề thử nghiệm “Doanh thu tăng 18%” và ID S1. Hàm kiểm tra ID của V1 chấp nhận S1. V2 đối chiếu tăng trưởng doanh thu AAPL FY2024 theo Form 10-K với giá trị khoảng 2,022% và trả `CONTRADICTED`. Thử nghiệm này đo sự khác nhau giữa hai quy tắc. Đánh giá đầu-cuối bằng cùng corpus, cùng ticker và cùng mốc cho Original, V1 và V2 vẫn chưa thực hiện. Xem [kết quả tái lập](benchmark-results.json).

Nguồn: [bài của Erik Taylor](https://medium.com/digital-mind/building-a-multi-tool-rag-agent-for-financial-analysis-6d4e667546a4), [repo Original](https://github.com/eriktaylor/ai-agent-moat/tree/a5e33e7bc2d094ba53b7671f65b3811185ceca33), [Apple FY2024 Form 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm).
