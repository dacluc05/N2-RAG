# Kiểm chứng và công thức

1. SEC Company Facts được chuẩn hóa theo concept, đơn vị, kỳ bắt đầu/kết thúc, ngày công bố và accession. Kỳ năm, quý riêng, lũy kế và số dư tại một thời điểm được giữ tách biệt. Công thức năm không cộng các bản YTD. Fact chỉ được chọn từ hồ sơ công bố vào hoặc trước mốc yêu cầu.
2. Agent nhận các đoạn đã truy xuất và phát biểu từng mệnh đề. Mỗi mệnh đề lưu ID đoạn và trích nguyên văn. Bộ kiểm tra loại bỏ bằng chứng sai CIK, sau mốc chốt, chưa có ngày, không có quyền lưu hoặc thiếu nội dung trích dẫn.
3. Nhận định số có cấu trúc được đối chiếu theo chỉ số, kỳ và đơn vị. Sai khác vượt sai số làm tròn được đánh dấu `CONTRADICTED`. Không có số liệu duy nhất cùng kỳ thì `UNVERIFIED`. Nhận định do Python tạo từ kết quả đã tính có thể được xác nhận bằng dữ liệu đầu vào. Nhận định của AI cần thêm đánh giá nội dung.
4. Reviewer nhận đoạn trích và các đoạn có khả năng phản bác trong một lượt riêng. Chỉ có ID đoạn thuộc tập bằng chứng gốc được chấp nhận. Mô hình và prompt kiểm chứng vẫn có thể sai. `PARTIALLY_SUPPORTED`, `UNVERIFIED` và `CONTRADICTED` xuất hiện trong trình kiểm chứng. Lead chọn ID đã được hỗ trợ.
5. Độ bao phủ là số nhóm có ít nhất một nhận định được hỗ trợ trên tám nhóm. Tỷ lệ hỗ trợ là số mệnh đề `SUPPORTED` chia cho số đã xét. Hai tỷ lệ này mô tả phiên chạy. Chúng không đo độ chính xác thực tế của mô hình.

| Chỉ số | Cách tính |
|---|---|
| Tăng trưởng doanh thu/lợi nhuận | (Kỳ này / kỳ trước − 1) × 100. So sánh hai năm tài chính liền nhau với khoảng cách ngày kết thúc từ 330 đến 390 ngày. |
| Biên gộp, hoạt động, ròng | Lợi nhuận tương ứng / doanh thu × 100. |
| ROA, ROE | Lợi nhuận ròng / tài sản hoặc vốn bình quân đầu–cuối kỳ × 100. |
| ROIC | Lợi nhuận hoạt động sau thuế ước tính / vốn đầu tư bình quân. Thuế hiệu dụng = thuế / lợi nhuận trước thuế. Vốn đầu tư = nợ vay + vốn chủ − tiền. |
| Thanh toán hiện hành | Tài sản ngắn hạn / nợ ngắn hạn. |
| Nợ vay/vốn chủ, nợ ròng | Nợ vay / vốn chủ và nợ vay − tiền. Nợ vay yêu cầu đủ các dòng nợ dài hạn đến hạn, nợ dài hạn còn lại và vay ngắn hạn. |
| FCF, biên FCF, chuyển đổi tiền | OCF − CapEx, FCF / doanh thu và OCF / lợi nhuận ròng. Khi thiếu khoản mua tài sản cố định riêng, khoản mua tài sản sản xuất có thể bao gồm cả tài sản vô hình. Bảng fact giữ concept gốc. |
| P/E, P/B, P/FCF | Vốn hóa ngày chạy chia lợi nhuận ròng, vốn chủ hoặc FCF kỳ năm gần nhất. |
| EV/EBITDA | (Vốn hóa + nợ ròng) / (lợi nhuận hoạt động + khấu hao). |
| DCF | Chiết khấu FCFF dự phóng và giá trị cuối kỳ, trừ nợ ròng, chia số cổ phiếu. Giá trị cuối kỳ = FCFF năm cuối × (1 + g) / (WACC − g). Độ nhạy gồm WACC và g dài hạn ±1 điểm phần trăm. |

Mẫu số không dương và dữ liệu thiếu trả `null`. Quy tắc ngành tài chính chặn các tỷ số không phù hợp dựa theo SIC. Nợ và EBITDA dùng những concept đã ánh xạ, có thể thiếu hoặc khác định nghĩa của nhà cung cấp dữ liệu. Các hệ số năm gần nhất không đại diện TTM.

## Giới hạn

- Phạm vi hiện tại là các doanh nghiệp Mỹ có dữ liệu US-GAAP thích hợp. IFRS, taxonomy tùy chỉnh, công thức chuyên biệt ngân hàng/bảo hiểm và dữ liệu Việt Nam chưa được chuẩn hóa đầy đủ.
- Danh mục ticker của SEC là ảnh chụp hiện hành. Chạy lịch sử không khôi phục được đầy đủ ticker đã hủy niêm yết hoặc thay đổi doanh nghiệp. Lịch sử giá Yahoo và Brave tắt trong phiên lịch sử để tránh trộn dữ liệu truy hồi hiện nay.
- Tài liệu PDF có thể mất cấu trúc bảng. PDF scan không được OCR tự động. Dữ liệu tài chính ưu tiên SEC Company Facts. Đoạn văn được lọc theo ngày công bố, còn hàm phát hiện câu “hiện tại” áp dụng ngưỡng 370 ngày khi nhận diện được ngôn ngữ thời gian.
- Chênh lệch XBRL cùng concept, đơn vị và khoảng kỳ được ghi lại. Giá trị từ lần công bố sau được chọn cho snapshot, dấu `resolved` thể hiện quy tắc ưu tiên ngày công bố. Trường này không phải kết luận SEC đã xác nhận đó là restatement.
- MiniLM ưu tiên nguồn tiếng Anh. Chưa đánh giá recall trên corpus nhiều công ty. Kết luận từ Gemini cần đối chiếu bằng Evidence Explorer.
- Brave không được dùng như nguồn để lưu đoạn trích. Danh sách host và quyền lưu áp dụng trước khi dữ liệu được đưa vào agent. Cài đặt mặc định có dữ liệu nguồn ngoài SEC hạn chế, do đó các phần định giá, thị trường và ngành có thể thiếu.
- Deadline được áp dụng theo thao tác I/O và ngân sách. Lần đầu tải model hoặc mã native cục bộ có thể kéo dài hơn deadline. Job queue một tiến trình không tự khôi phục job đang chạy.
