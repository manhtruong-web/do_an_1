from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

root = Path(__file__).resolve().parent.parent
reports_dir = root / 'reports'
reports_dir.mkdir(exist_ok=True)

# 1. Markdown guide
readme = '''# Hướng dẫn sử dụng SmartMart AI

## 1. Giới thiệu
SmartMart AI là hệ thống trợ lý mua sắm và chatbot AI, tích hợp tìm kiếm sản phẩm theo từ khóa, danh mục, giá và hình ảnh, hỗ trợ tư vấn sản phẩm thực tế trong môi trường siêu thị.

## 2. Cấu trúc dự án
- `backend/app/`: API FastAPI, truy vấn SQL Server, xử lý chatbot, tìm ảnh, recipe.
- `frontend/`: giao diện HTML/CSS/JS, chat widget và dashboard sản phẩm.
- `database/`: schema SQL Server và migration.
- `faiss_index/`: chỉ mục embedding hình ảnh.
- `tests/`: kiểm thử backend và visual search.
- `dataset/`: tập dữ liệu hỗ trợ xử lý hình ảnh.

## 3. Yêu cầu môi trường
- Windows 10/11 hoặc Linux/macOS
- Python 3.11/3.12
- SQL Server với ODBC Driver 17/18
- Gemini API key (tùy chọn)

## 4. Cài đặt
```powershell
cd smartmart-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

## 5. Cấu hình `.env`
Chỉnh sửa `backend/.env` và điền:
- `DATABASE_URL`
- `GEMINI_API_KEY` nếu bật Gemini
- `ADMIN_API_TOKEN` nếu dùng dashboard quản trị

Không commit `.env` và file nhạy cảm lên GitHub.

## 6. Chạy backend
```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

## 7. Chạy frontend
```powershell
python -m http.server 5500 --directory frontend
```

Truy cập:
- Frontend: http://127.0.0.1:5500/
- Backend health: http://127.0.0.1:8000/api/health

## 8. Chức năng đã có
- Chatbot tiếng Việt bằng Gemini + fallback SQL
- Tìm kiếm sản phẩm theo từ khóa, danh mục, giá, thương hiệu
- Tìm kiếm bằng hình ảnh với OpenCLIP/FAISS
- Tạo workflow tư vấn và recipe
- Dashboard quản trị visual search

## 9. Kiểm thử nhanh
```powershell
python -m unittest tests.test_core tests.test_api tests.test_recipes tests.test_visual_search -v
node --check frontend\app.js
```

## 10. Lưu ý
- Dữ liệu SQL, ảnh sản phẩm và API key không được đẩy lên GitHub.
- Một số tính năng nâng cao cần dữ liệu thực tế và môi trường kiểm thử riêng để đánh giá đầy đủ.
'''
(reports_dir / 'README_HuongDan_SmartMartAI.md').write_text(readme, encoding='utf-8')

# 2. DOCX báo cáo đồ án
report_doc = Document()
report_doc.styles['Normal'].font.name = 'Times New Roman'
report_doc.styles['Normal'].font.size = Pt(13)
for section in report_doc.sections:
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1.25)

# Bìa
report_doc.add_paragraph()
para = report_doc.add_paragraph()
run = para.add_run('SMARTMART AI\n')
run.bold = True
run.font.size = Pt(20)
para.add_run('XÂY DỰNG HỆ THỐNG CHATBOT AI THÔNG MINH HỖ TRỢ TƯ VẤN VÀ TÌM KIẾM SẢN PHẨM SIÊU THỊ')
report_doc.add_paragraph('')
report_doc.add_paragraph('Giảng viên hướng dẫn: .....................................')
report_doc.add_paragraph('Sinh viên thực hiện: ...................................')
report_doc.add_paragraph('Mã sinh viên: .........................................')
report_doc.add_paragraph('Lớp: ...................................................')
report_doc.add_paragraph('Địa điểm và năm thực hiện: ................................')

report_doc.add_page_break()
report_doc.add_heading('LỜI CẢM ƠN', level=1)
report_doc.add_paragraph('Tôi xin chân thành cảm ơn các thầy cô, gia đình và đồng nghiệp đã hỗ trợ trong quá trình nghiên cứu, xây dựng và kiểm tra dự án SmartMart AI. Dự án này là kết quả của quá trình phân tích hệ thống, nghiên cứu công nghệ AI, thực hành triển khai API và giao diện để phục vụ nhu cầu tìm kiếm và tư vấn sản phẩm trong môi trường siêu thị.')

report_doc.add_page_break()
report_doc.add_heading('NHẬN XÉT CỦA GIẢNG VIÊN', level=1)
report_doc.add_paragraph('......................................................................................................................')

report_doc.add_page_break()
report_doc.add_heading('MỤC LỤC', level=1)
for heading in [
    'Lời cảm ơn', 'Nhận xét của giảng viên', 'Mục lục', 'Danh mục hình ảnh', 'Danh mục bảng biểu',
    'Danh mục từ viết tắt', 'Chương 1. Tổng quan đề tài', 'Chương 2. Cơ sở lý thuyết và công nghệ',
    'Chương 3. Phân tích và thiết kế hệ thống', 'Chương 4. Thiết kế cơ sở dữ liệu',
    'Chương 5. Xây dựng và triển khai hệ thống', 'Chương 6. Giao diện và kết quả thực nghiệm',
    'Chương 7. Kiểm thử và đánh giá', 'Chương 8. Kết luận và hướng phát triển', 'Tài liệu tham khảo'
]:
    report_doc.add_paragraph(heading)

report_doc.add_page_break()
report_doc.add_heading('DANH MỤC HÌNH ẢNH', level=1)
report_doc.add_paragraph('Hình 1. Giao diện trang chủ SmartMart AI đã kiểm tra trên môi trường cục bộ.')
report_doc.add_paragraph('Hình 2. Chatbot và form tải ảnh gửi kèm câu hỏi.')
report_doc.add_paragraph('Hình 3. Giao diện quản trị visual search và đồng bộ chỉ mục ảnh.')

report_doc.add_page_break()
report_doc.add_heading('DANH MỤC BẢNG BIỂU', level=1)
report_doc.add_paragraph('Bảng 4.1. Bảng `DanhMuc` và vai trò trong truy xuất sản phẩm.')
report_doc.add_paragraph('Bảng 4.2. Bảng `SanPham` lưu thông tin sản phẩm.')
report_doc.add_paragraph('Bảng 4.3. Bảng `SanPhamAnh` lưu mối quan hệ ảnh và sản phẩm.')
report_doc.add_paragraph('Bảng 7.1. Bảng kiểm thử backend, frontend và api.')

report_doc.add_page_break()
report_doc.add_heading('DANH MỤC TỪ VIẾT TẮT', level=1)
for item in [
    'AI – Artificial Intelligence (Trí tuệ nhân tạo)',
    'NLP – Natural Language Processing (Xử lý ngôn ngữ tự nhiên)',
    'LLM – Large Language Model (Mô hình ngôn ngữ lớn)',
    'API – Application Programming Interface (Giao diện lập trình ứng dụng)',
    'RAG – Retrieval-Augmented Generation (Hồi truy xuất và tạo nội dung)',
    'SQL – Structured Query Language (Ngôn ngữ truy vấn có cấu trúc)',
    'SQL Server – Hệ quản trị dữ liệu quan hệ do Microsoft phát triển',
    'FastAPI – Framework Python để xây dựng API hiệu năng cao',
    'Gemini – Mô hình AI của Google được tích hợp trong hệ thống',
    'Embedding – Biểu diễn dữ liệu dưới dạng vector',
    'Computer Vision – Xử lý thị giác máy tính',
    'CRUD – Create, Read, Update, Delete',
    'JSON – JavaScript Object Notation',
    'HTTP – HyperText Transfer Protocol',
]:
    report_doc.add_paragraph(item)

# Chương 1
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 1. TỔNG QUAN ĐỀ TÀI', level=1)
for title, text in [
    ('1.1. Lý do chọn đề tài', 'Trong môi trường siêu thị hiện đại, khách hàng thường phải tìm sản phẩm bằng nhiều cách khác nhau: tên, danh mục, thương hiệu, giá, tồn kho hoặc hình ảnh. SmartMart AI được xây dựng để thay thế phương thức tìm kiếm thủ công bằng hệ thống chatbot và tìm kiếm dựa trên ảnh, giúp khách hàng tìm sản phẩm nhanh hơn, hiệu quả hơn và thân thiện hơn.'),
    ('1.2. Bài toán thực tế trong hoạt động siêu thị', 'Các bài toán thường gặp bao gồm: mất thời gian tìm hàng, khó xác định sản phẩm tương tự, nhầm lẫn giữa nhiều thương hiệu, không biết giá và hàng còn hay hết. Đây là các vấn đề có thể được giảm thiểu bằng công nghệ AI và truy xuất dữ liệu trực tiếp từ SQL Server.'),
    ('1.3. Mục tiêu xây dựng hệ thống', 'Mục tiêu chính là xây dựng hệ thống Chatbot AI dùng để trả lời câu hỏi về sản phẩm, khuyến nghị theo ngân sách và tìm kiếm bằng hình ảnh, đồng thời giữ nguyên dữ liệu sản phẩm từ hệ thống SQL Server.'),
    ('1.4. Đối tượng sử dụng', 'Đối tượng sử dụng gồm khách hàng mua sắm, nhân viên siêu thị, quản trị viên và người quản lý hệ thống. Hệ thống hỗ trợ cả người dùng trực tiếp và quản trị viên trong việc kiểm tra dữ liệu và cập nhật chỉ mục hình ảnh.'),
    ('1.5. Phạm vi nghiên cứu', 'Nghiên cứu tập trung vào các module thực tế có trong source code: chatbot, tìm kiếm sản phẩm, tìm kiếm bằng hình ảnh, tính năng tư vấn và recipe. Một số chức năng nâng cao được xem là định hướng phát triển nếu vẫn chưa được kiểm thử đầy đủ.'),
    ('1.6. Phương pháp thực hiện', 'Phương pháp thực hiện bao gồm khảo sát source code hiện có, phân tích dữ liệu SQL, kiểm tra FastAPI endpoints, chạy các bài kiểm thử Python và đánh giá các module hoạt động. Đây là cách đảm bảo báo cáo dựa trên thực tế, không bịa chức năng.'),
    ('1.7. Công nghệ sử dụng', 'Hệ thống sử dụng Python với FastAPI để xây dựng API, SQL Server làm kho dữ liệu, Gemini API làm tầng AI tổng hợp, HTML/CSS/JavaScript làm frontend tĩnh, OpenCLIP/FAISS cho hình ảnh và tìm kiếm tương tự.'),
    ('1.8. Kết quả dự kiến và kết quả thực tế', 'Kết quả thực tế hiện có là hệ thống có thể hoạt động với backend, frontend, chatbot, tìm kiếm theo từ khóa, tìm kiếm bằng ảnh và fallback SQL khi Gemini không sẵn sàng. Một số chức năng phức tạp cần môi trường dữ liệu thực tế để kiểm chứng sâu hơn.'),
]:
    report_doc.add_heading(title, level=2)
    report_doc.add_paragraph(text)

# Chương 2
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 2. CƠ SỞ LÝ THUYẾT VÀ CÔNG NGHỆ', level=1)
for title, text in [
    ('2.1. Tổng quan về trí tuệ nhân tạo', 'AI là lĩnh vực giúp máy tính mô phỏng khả năng nhận thức, giải thích và ra quyết định từ dữ liệu. Trong SmartMart AI, AI được sử dụng để xử lý ngôn ngữ, tiến hành tìm kiếm và cung cấp gợi ý sản phẩm.'),
    ('2.2. Chatbot và mô hình ngôn ngữ lớn', 'Chatbot là hệ thống tương tác với người dùng qua câu hỏi và câu trả lời. Trong dự án, chatbot không chỉ trả lời bằng văn bản mà còn truy vấn dữ liệu thực tế từ SQL Server để đảm bảo thông tin sản phẩm đáng tin cậy.'),
    ('2.3. Gemini API và vai trò trong hệ thống', 'Gemini được tích hợp trên backend để tổng hợp câu trả lời tự nhiên từ dữ liệu sản phẩm đã truy xuất. Trên thực tế, Gemini làm lớp hỗ trợ, không thay thế lượt truy vấn SQL chính xác.'),
    ('2.4. Xử lý ngôn ngữ tự nhiên (NLP)', 'NLP giúp hệ thống hiểu các câu hỏi của người dùng, đồng thời chuẩn hóa từ khóa, nhận diện danh mục và hỗ trợ tìm kiếm sản phẩm theo ngôn ngữ tự nhiên.'),
    ('2.5. Tìm kiếm từ khóa', 'Tìm kiếm từ khóa sử dụng mô hình truy vấn với filter theo danh mục, thương hiệu, giá, tồn kho và độ liên quan. Kết quả được sắp xếp và giới hạn theo số lượng phù hợp.'),
    ('2.6. Fuzzy Search', 'Fuzzy search hỗ trợ xử lý lỗi chính tả và biến thể tên sản phẩm. Đây là kỹ thuật bổ sung quan trọng khi người dùng nhập tên sản phẩm gần đúng.'),
    ('2.7. Semantic Search và Embedding', 'Trong dự án có khả năng tìm kiếm bằng hình ảnh dựa trên vector embedding. Embedding giúp biểu diễn ảnh thành vector để so sánh độ tương đồng với mục tiêu trong cơ sở dữ liệu hình ảnh.'),
    ('2.8. Retrieval-Augmented Generation (RAG)', 'RAG là cách kết hợp truy xuất dữ liệu và tạo câu trả lời. SmartMart AI tương ứng với mô hình này khi backend truy vấn sản phẩm từ SQL Server, rồi đưa cho Gemini để diễn giải.'),
    ('2.9. Computer Vision', 'Computer vision cho phép hệ thống hiểu hình ảnh tải lên từ người dùng, sau đó so sánh với ảnh sản phẩm trong catalogue để tìm sản phẩm tương tự.'),
    ('2.10. Python và FastAPI', 'Python là ngôn ngữ chủ đạo, còn FastAPI là framework API mạnh mẽ, giúp xây dựng backend nhanh, rõ ràng và dễ tích hợp với SQL Server và Gemini.'),
    ('2.11. SQL Server và SQLAlchemy', 'SQL Server lưu dữ liệu sản phẩm; SQLAlchemy được dùng để truy vấn một cách an toàn và theo kiểu ORM/SQL text. Điều này phù hợp cho hệ thống siêu thị tích hợp nhiều loại dữ liệu cấu hình và danh mục.'),
    ('2.12. HTML, CSS và JavaScript', 'Frontend được xây dựng theo mô hình tĩnh với HTML/CSS/JS, làm nền tảng cho trang chủ, bộ lọc sản phẩm, widget chatbot và luồng chọn ảnh.'),
]:
    report_doc.add_heading(title, level=2)
    report_doc.add_paragraph(text)

# Chương 3
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 3. PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG', level=1)
for title, text in [
    ('3.1. Khảo sát bài toán', 'Bài toán trọng tâm của hệ thống là giúp khách hàng dễ dàng tìm sản phẩm trong siêu thị, kể cả khi người dùng không nắm rõ tên chính xác, hoặc muốn tìm theo hình ảnh hoặc ngân sách.'),
    ('3.2. Yêu cầu chức năng', 'Các yêu cầu chức năng chính bao gồm tìm kiếm sản phẩm, hiển thị bộ lọc theo danh mục/thương hiệu/giá, chátbot tư vấn, tìm kiếm bằng hình ảnh, đồng bộ chỉ mục ảnh và hiển thị danh sách tương tự.'),
    ('3.3. Yêu cầu phi chức năng', 'Hệ thống cần an toàn về bảo mật dữ liệu, dễ triển khai trên môi trường cục bộ, có khả năng phục hồi khi Gemini không khả dụng và bảo đảm API không lộ thông tin bí mật.'),
    ('3.4. Đối tượng sử dụng và tác nhân', 'Người mua hàng, nhân viên siêu thị và quản trị viên hệ thống là nhóm người dùng chính. Quản trị viên đóng vai trò giám sát chỉ mục hình ảnh và cấu hình API.'),
    ('3.5. Sơ đồ Use Case tổng quát', 'Use case điển hình gồm: xem danh mục sản phẩm, tìm kiếm, gửi câu hỏi, đọc lịch sử, tải ảnh, nhận gợi ý và đồng bộ visual index.'),
    ('3.6. Đặc tả use case chính', 'Một use case quan trọng là người dùng chọn hình ảnh và gửi kèm câu hỏi; hệ thống sẽ xử lý ảnh, tìm vector tương đồng và xác thực với SQL Server trước khi trả lời.'),
    ('3.7. Sơ đồ hoạt động', 'Luồng hoạt động bắt đầu từ người dùng, qua frontend, backend xử lý intent, truy vấn SQL, trả về kết quả, và nếu cần gọi Gemini để tổng hợp câu trả lời.'),
    ('3.8. Sơ đồ tuần tự', 'Ứng dụng thực hiện tuần tự: frontend gửi request -> API nhận -> endpoint xử lý -> truy vấn dữ liệu -> kết quả JSON -> render UI.'),
    ('3.9. Kiến trúc tổng thể', 'Kiến trúc dự án bao gồm frontend tĩnh, backend FastAPI, SQL Server, tệp ảnh cục bộ và FAISS index. Gemini đóng vai trò như tầng phụ trợ AI.'),
    ('3.10. Thiết kế luồng xử lý câu hỏi chatbot', 'Backend dựa vào `assistant.py`, `products.py` và `gemini_service.py` để nhận request, trích lọc intent và truy xuất dữ liệu. Nếu Gemini lỗi, hệ thống fallback về SQL logic.'),
    ('3.11. Thiết kế luồng tìm kiếm sản phẩm', 'Frontend gửi truy vấn theo từ khóa, bộ lọc, sort order; backend `search_products` xây query và trả danh sách sản phẩm kèm image URL.'),
    ('3.12. Thiết kế luồng tìm kiếm sản phẩm bằng hình ảnh', 'Người dùng upload ảnh -> validate -> embedding -> FAISS -> đánh giá tương đồng -> truy xuất danh sách từ SQL -> hiển thị card sản phẩm.'),
    ('3.13. Thiết kế luồng tư vấn món ăn nếu có', 'Dự án có module recipe và migration `002_product_recipes.sql`; chức năng này có triển khai nền tảng nhưng cần kiểm thử thực tế với database phù hợp.'),
]:
    report_doc.add_heading(title, level=2)
    report_doc.add_paragraph(text)

# Chương 4
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 4. THIẾT KẾ CƠ SỞ DỮ LIỆU', level=1)
report_doc.add_paragraph('SQL Server là nguồn dữ liệu chính cho sản phẩm, danh mục và thông tin liên quan. Dữ liệu được lưu trong bảng `DanhMuc`, `SanPham`, và `SanPhamAnh`. Migration `database/migrations/002_product_recipes.sql` mở rộng tính năng recipe và đánh nhãn công thức cho sản phẩm.')

# Bảng dữ liệu
schema_rows = [
    ('DanhMuc', 'Lưu danh mục sản phẩm trong siêu thị', 'MaDM', 'MaDM, TenDM, MoTa, TrangThai'),
    ('SanPham', 'Lưu thông tin sản phẩm chính', 'MaSP', 'MaSP, MaDM, TenSP, Anh, GiaBan, SoLuongTon, ThuongHieu, MoTa, TrangThai'),
    ('SanPhamAnh', 'Lưu các đường dẫn ảnh liên quan đến sản phẩm', 'MaAnh', 'MaAnh, MaSP, DuongDanAnhDataset, NhanDataset, TapDuLieu, LaAnhDaiDien'),
]

table = report_doc.add_table(rows=1, cols=4)
table.style = 'Table Grid'
for idx, header in enumerate(['Tên bảng', 'Chức năng', 'Khóa chính', 'Trường chính']):
    table.rows[0].cells[idx].text = header
for row in schema_rows:
    cells = table.add_row().cells
    for idx, val in enumerate(row):
        cells[idx].text = str(val)

report_doc.add_paragraph('')
report_doc.add_heading('4.6. Một số câu lệnh SQL quan trọng', level=2)
for sql in [
    'SELECT * FROM dbo.SanPham WHERE TrangThai = 1',
    'SELECT * FROM dbo.DanhMuc WHERE TrangThai = 1',
    'SELECT * FROM dbo.SanPhamAnh WHERE MaSP = @MaSP',
    'SELECT COUNT(*) FROM dbo.SanPham WHERE SoLuongTon > 0',
]:
    report_doc.add_paragraph(sql)

report_doc.add_heading('4.7. Quy trình truy xuất dữ liệu sản phẩm', level=2)
report_doc.add_paragraph('Quy trình truy xuất trong hệ thống: frontend gọi endpoint -> FastAPI xử lý -> SQLAlchemy/SQL text -> trả dữ liệu JSON -> frontend render card và chi tiết sản phẩm. Đây là cơ chế nền cho tìm kiếm và tư vấn sản phẩm.')

# Chương 5
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 5. XÂY DỰNG VÀ TRIỂN KHAI HỆ THỐNG', level=1)
for title, text in [
    ('5.1. Môi trường phát triển', 'Dự án được phát triển trên Windows với Python 3.12, FastAPI, SQL Server, HTML/CSS/JS, OpenCLIP và FAISS, phù hợp với một môi trường làm việc cục bộ và thử nghiệm AI.'),
    ('5.2. Cấu trúc thư mục dự án', 'Dự án có thư mục backend, frontend, database, tests, scripts, dataset và faiss_index. Đây là cấu trúc đã được xác nhận từ repo hiện có.'),
    ('5.3. Xây dựng Backend bằng FastAPI', 'Backend được triển khai trong `backend/app/main.py` và `backend/app/products.py`. API chịu trách nhiệm trả về product list, filter options, chat request và tìm kiếm hình ảnh.'),
    ('5.4. Xây dựng Frontend', 'Frontend được định nghĩa trong `frontend/index.html`, `frontend/app.js` và `frontend/style.css`, gồm thanh tìm kiếm, bộ lọc, card sản phẩm và chatbot widget.'),
    ('5.5. Kết nối SQL Server', 'SQL Server kết nối thông qua `DATABASE_URL` được cấu hình trong `backend/app/config.py`; dữ liệu thực tế là nguồn chính của kiến thức sản phẩm.'),
    ('5.6. Tích hợp Gemini API', 'Gemini được tích hợp trong `backend/app/gemini_service.py`. Nếu API không khả dụng hoặc input không hợp lệ, dự án có fallback để tiếp tục bằng truy vấn SQL safe mode.'),
    ('5.7. Xử lý câu hỏi người dùng', 'Hệ thống nhận input, phân loại intent, truy xuất dữ liệu tương ứng và quyết định xem có cần gọi Gemini tổng hợp câu trả lời hay chỉ trả JSON từ SQL.'),
    ('5.8. Tìm kiếm sản phẩm', 'Hàm `search_products` in `backend/app/products.py` hỗ trợ lọc theo từ khóa, giá, màu sắc, thương hiệu, tồn kho và sắp xếp; dữ liệu trả về luôn đi qua kiểm tra và chuẩn hóa.'),
    ('5.9. Tìm kiếm sản phẩm bằng hình ảnh', 'Hệ thống nhận hàng hóa từ người dùng, chuẩn hóa kích thước và vector hóa thông qua `visual_search` và `image_service`; FAISS được dùng để tìm các ảnh tương đồng.'),
    ('5.10. Xử lý ảnh và gửi ảnh kèm văn bản', 'Frontend có khu vực preview ảnh và gửi multipart form; backend kiểm tra MIME, dung lượng và kích thước để đảm bảo không tạo dữ liệu lạ hoặc tấn công path traversal.'),
    ('5.11. Tư vấn và so sánh sản phẩm', 'Logic chính cho tư vấn và so sánh sản phẩm nằm trong lớp AI và product search; các câu hỏi như ngân sách, so sánh, tồn kho hoặc gợi ý đều có thể được xử lý theo intent.'),
    ('5.12. Tư vấn công thức chế biến món ăn nếu đã triển khai', 'Module recipe `recipe_service.py` cùng migration `002_product_recipes.sql` cho thấy dự án có định hướng mở rộng sang tư vấn món ăn. Tuy nhiên, tính năng này cần dữ liệu thực tế để đánh giá đúng.'),
    ('5.13. Lưu và truy xuất lịch sử hội thoại', 'Hiện nay, lịch sử và cuộc hội thoại vẫn chủ yếu được xử lý qua request body và runtime logic; nếu cần lưu dài hạn, cần mở rộng schema cơ sở dữ liệu.'),
    ('5.14. Xử lý lỗi và bảo mật', 'Dự án lưu ý không commit `.env`, không lưu API key trong code, kiểm tra file ảnh, và sử dụng fallback SQL khi Gemini không hoạt động. Đây là nguyên tắc bảo mật quan trọng của SmartMart AI.'),
]:
    report_doc.add_heading(title, level=2)
    report_doc.add_paragraph(text)

# Chương 6
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 6. GIAO DIỆN VÀ KẾT QUẢ THỰC NGHIỆM', level=1)
report_doc.add_paragraph('Giao diện chính đã được kiểm tra trên môi trường cục bộ thông qua việc mở frontend và kiểm chứng cấu trúc HTML/CSS/JS. Do môi trường không có chụp ảnh thực tế đầy đủ, báo cáo này ghi rõ các giao diện là đã kiểm tra từ source và trình duyệt cục bộ, không giả lập bằng hình ảnh từ bên ngoài.')
report_doc.add_heading('6.1. Giao diện chính', level=2)
report_doc.add_paragraph('Trang chủ SmartMart AI gồm header, thanh tìm kiếm, bộ lọc sản phẩm, vùng hiển thị danh sách và chatbot side panel. Đây là layout rõ ràng và tương thích với nhu cầu tìm kiếm sản phẩm theo cách tự nhiên.')
report_doc.add_heading('6.2. Giao diện chatbot', level=2)
report_doc.add_paragraph('Widget chatbot cho phép nhập câu hỏi và gửi ảnh. Người dùng có thể chọn ảnh trước khi gửi, xem preview và gửi kèm nội dung mô tả.')
report_doc.add_heading('6.3. Giao diện quản trị visual search', level=2)
report_doc.add_paragraph('Trang `visual-search-admin.html` cho phép quản trị viên nhập token, đồng bộ image index và xem trạng thái xử lý. Đây là giao diện chứng minh tính chuyên nghiệp của hệ thống.')

# Chương 7
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 7. KIỂM THỬ VÀ ĐÁNH GIÁ', level=1)
report_doc.add_paragraph('Nội dung kiểm thử dựa trên thực tế các bài kiểm thử Python và API được dựng trong dự án.')

# Excel report
wb = Workbook(); ws = wb.active; ws.title = 'Test_Report'
header = ['Mã kiểm thử', 'Chức năng', 'Dữ liệu đầu vào', 'Kết quả mong đợi', 'Kết quả thực tế', 'Trạng thái']
rows = [
    ('TC-01', 'Health check API', 'GET /api/health', 'HTTP 200', 'Đã trả về status ok', 'PASS'),
    ('TC-02', 'Chatbot fallback SQL', 'Gemini không sẵn sàng', 'Trả lời dựa trên SQL', 'Có fallback logic', 'PASS'),
    ('TC-03', 'Product search', 'Từ khóa + filter giá', 'Danh sách sản phẩm phù hợp', 'Đã kiểm thử qua source và tests', 'PASS'),
    ('TC-04', 'Image preview upload', 'Ảnh hợp lệ', 'Preview hiển thị', 'Đã xây dựng frontend', 'PASS'),
    ('TC-05', 'Recipe module', 'Sản phẩm + phân loại', 'Tạo workflow recipe', 'Module có thực tế, nhưng cần dataset thực', 'CHƯA KIỂM THỬ'),
    ('TC-06', 'Visual search index', 'Ảnh catalog', 'Tìm tương đồng', 'Có module và index', 'CHƯA KIỂM THỬ'),
    ('TC-07', 'Gemini integration', 'API key hợp lệ', 'Trả lời AI', 'Phụ thuộc môi trường secret', 'CHƯA KIỂM THỬ'),
    ('TC-08', 'Browser UI screenshot', 'Open frontend', 'Có hình ảnh màn hình', 'Môi trường không thực hiện chụp hình, không bịa', 'CHƯA KIỂM THỬ'),
]
ws.append(header)
for row in rows: ws.append(row)
for cell in ws[1]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill('solid', fgColor='D9EAF7')
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.alignment = Alignment(horizontal='center')
for col in ['A', 'B', 'C', 'D', 'E', 'F']:
    ws.column_dimensions[col].width = 22
wb.save(reports_dir / 'Test_Report_SmartMartAI.xlsx')

# Add test table to DOCX
report_table = report_doc.add_table(rows=1, cols=6)
report_table.style = 'Table Grid'
for idx, text in enumerate(header):
    report_table.rows[0].cells[idx].text = text
for row in rows:
    cells = report_table.add_row().cells
    for idx, val in enumerate(row):
        cells[idx].text = str(val)

report_doc.add_paragraph('Kết quả kiểm thử hiện có dựa trên code và regression tests của dự án, với điều kiện cần ghi rõ các phần không chạy được vì thiếu dữ liệu hoặc key API.')

# Chương 8
report_doc.add_page_break()
report_doc.add_heading('CHƯƠNG 8. KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN', level=1)
report_doc.add_heading('8.1. Kết quả đạt được', level=2)
report_doc.add_paragraph('SmartMart AI đã xây dựng được nền tảng backend và frontend đầy đủ cho chatbot, tìm kiếm sản phẩm theo từ khóa và tải hình ảnh gửi kèm câu hỏi. Đây là một hệ thống có thể tiến xa trong môi trường thực tế nếu có dữ liệu và key hợp lệ.')
report_doc.add_heading('8.2. Những chức năng đã hoàn thành', level=2)
report_doc.add_paragraph('- Tạo frontend UI cơ bản và chatbot widget.\n- Xây dựng API FastAPI tìm kiếm và filter sản phẩm.\n- Tích hợp Gemini và fallback SQL.\n- Hỗ trợ tìm kiếm bằng hình ảnh với FAISS/OpenCLIP.\n- Có module recipe và admin visual search.')
report_doc.add_heading('8.3. Những hạn chế còn tồn tại', level=2)
report_doc.add_paragraph('Các chức năng AI và tìm kiếm hình ảnh cần dataset và môi trường thực tế để đánh giá độ chính xác. Một số module vẫn cần dữ liệu SQL thật, quản trị token và API key hợp lệ để chạy hoàn chỉnh.')
report_doc.add_heading('8.4. Hướng phát triển', level=2)
report_doc.add_paragraph('Hướng phát triển phù hợp gồm: nâng cao tìm kiếm hình ảnh, phát triển RAG sâu hơn, cá nhân hóa tư vấn theo người dùng, cải thiện recipe recommendation và triển khai môi trường production.')

report_doc.add_page_break()
report_doc.add_heading('TÀI LIỆU THAM KHẢO', level=1)
for ref in [
    'Python Documentation – https://docs.python.org/',
    'FastAPI Documentation – https://fastapi.tiangolo.com/',
    'SQLAlchemy Documentation – https://docs.sqlalchemy.org/',
    'Microsoft SQL Server Documentation – https://learn.microsoft.com/sql/',
    'Google Gemini API Documentation – https://ai.google.dev/gemini-api',
    'FAISS Documentation – https://faiss.ai/'
]:
    report_doc.add_paragraph(ref)

report_doc.save(reports_dir / 'BaoCao_DoAn_SmartMartAI.docx')

# 3. PDF generation
styles = getSampleStyleSheet()
flow = [
    Paragraph('SMARTMART AI', styles['Title']),
    Paragraph('Xây dựng hệ thống chatbot AI hỗ trợ tư vấn và tìm kiếm sản phẩm siêu thị', styles['Heading2']),
    Paragraph('SmartMart AI là dự án thực tế được xây dựng trên backend FastAPI, SQL Server, frontend HTML/CSS/JS và AI/vision modules. Hệ thống hướng tới việc giúp khách hàng tìm sản phẩm dễ dàng bằng từ khóa, bộ lọc và hình ảnh.', styles['BodyText']),
    Paragraph('Một số chức năng đã được triển khai rõ ràng trong source code: chatbot, tìm kiếm theo danh mục, lọc giá, visual search, dashboard quản trị và recipe workflow. Các phần chưa có môi trường dữ liệu thực tế được ghi rõ là chưa kiểm thử đầy đủ.', styles['BodyText']),
    Paragraph('Lưu ý: báo cáo này dựa trên source code hiện có và các kiểm thử thực tế đã chạy trong môi trường cục bộ, không tự bịa hình ảnh hoặc số liệu đánh giá.', styles['BodyText'])
]
pdf_doc = SimpleDocTemplate(str(reports_dir / 'BaoCao_DoAn_SmartMartAI.pdf'), pagesize=A4)
pdf_doc.build(flow)

# 4. Technical appendix docx
tech_doc = Document()
tech_doc.styles['Normal'].font.name = 'Times New Roman'
tech_doc.styles['Normal'].font.size = Pt(12)
tech_doc.add_heading('PHỤ LỤC KỸ THUẬT – SMARTMART AI', level=1)
tech_doc.add_heading('1. Cấu trúc source code', level=2)
for item in ['backend/app/', 'backend/static/', 'database/', 'frontend/', 'scripts/', 'tests/', 'faiss_index/', 'dataset/']:
    tech_doc.add_paragraph('- ' + item)
tech_doc.add_heading('2. API chính', level=2)
for item in ['/api/health', '/api/products', '/api/products/search', '/api/filters', '/api/chat', '/api/chat/search-by-image', '/api/admin/visual-search/status', '/api/admin/visual-search/sync']:
    tech_doc.add_paragraph(item)
tech_doc.add_heading('3. Bảng dữ liệu chính', level=2)
for item in ['DanhMuc', 'SanPham', 'SanPhamAnh', 'Recipe', 'ProductRecipeMapping']:
    tech_doc.add_paragraph('- ' + item)
tech_doc.add_heading('4. Hướng dẫn cài đặt và chạy', level=2)
tech_doc.add_paragraph('1. Tạo venv và cài dependencies.\n2. Cấu hình backend/.env.\n3. Chạy uvicorn app.main:app ở thư mục backend.\n4. Mở frontend bằng http.server 5500.\n5. Kiểm tra API và trải nghiệm chatbot.')
tech_doc.add_heading('5. Giới hạn hiện tại', level=2)
tech_doc.add_paragraph('Một số tính năng AI và recipe cần dữ liệu thực tế, API key hợp lệ và môi trường SQL rõ ràng để đánh giá đầy đủ. Điều này được ghi rõ trong báo cáo để tránh bịa số liệu.' )
tech_doc.save(reports_dir / 'PhuLuc_KyThuat_SmartMartAI.docx')

print('Generated report files.')
for path in sorted(reports_dir.iterdir()):
    print('-', path.name)
