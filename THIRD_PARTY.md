# Nguồn và thành phần bên thứ ba

- [Erik Taylor, Building a Multi-Tool RAG Agent for Financial Analysis](https://medium.com/digital-mind/building-a-multi-tool-rag-agent-for-financial-analysis-6d4e667546a4) và [ai-agent-moat](https://github.com/eriktaylor/ai-agent-moat) là nguồn phương pháp. ZIP không chứa mã gốc hay bản PDF.
- [SEC EDGAR](https://www.sec.gov/about/developer-resources) là nguồn dữ liệu tài chính chính thức. Fixture Apple trích một số dữ kiện số học có liên kết hồ sơ gốc. Mọi dữ liệu mô phỏng khác dùng trong test đều được gắn nhãn.
- Mã ZIP tham chiếu thư viện Python cài riêng, trong đó PyMuPDF và FAISS có giấy phép theo dự án tương ứng. Người triển khai chịu trách nhiệm xem điều khoản của các phụ thuộc và nguồn nội dung cho trường hợp sử dụng của mình.
- Brave, Gemini và Yahoo Finance có điều khoản và hạn mức theo tài khoản hoặc dịch vụ. Công cụ không lưu phản hồi Brave. Mặc định không lưu dữ liệu Yahoo. Chỉ bật tùy chọn lưu dữ liệu khi được phép.
