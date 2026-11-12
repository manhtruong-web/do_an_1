# SmartMart AI

Website siêu thị tích hợp chatbot AI tiếng Việt và tìm kiếm sản phẩm bằng hình ảnh.

SmartMart AI Shopping Assistant hỗ trợ hội thoại, gợi ý theo tồn kho và kiểm
soát không bịa dữ liệu.

## Chức năng chính

- Chatbot tiếng Việt dùng Gemini, có fallback truy vấn SQL khi Gemini không khả dụng.
- Tìm kiếm sản phẩm theo từ khóa, giá, danh mục và tồn kho trên SQL Server.
- Tìm sản phẩm tương tự bằng ảnh với OpenCLIP/FAISS; Gemini Vision là tùy chọn.
- Tư vấn và tạo công thức AI dựa trên sản phẩm thực tế; công thức mới cần được duyệt.
- Giao diện quản trị để đồng bộ chỉ mục ảnh, được bảo vệ bằng token quản trị.

## Cấu trúc dự án

- `backend/app/`: API FastAPI, truy vấn SQL, chatbot, tìm ảnh và công thức.
- `backend/static/`: thư mục ảnh sản phẩm cục bộ; ảnh danh mục không được đóng gói trong Git.
- `database/`: schema cơ sở dữ liệu và migration.
- `frontend/`: giao diện HTML/CSS/JavaScript thuần.
- `scripts/`: công cụ đồng bộ ảnh, đánh giá tìm kiếm và tạo công thức.
- `tests/`: kiểm thử backend và tìm kiếm ảnh.

## Yêu cầu môi trường

- Windows 10/11 hoặc Linux/macOS; Python 3.11 hoặc 3.12.
- SQL Server truy cập được từ máy chạy backend và Microsoft ODBC Driver 17/18.
- Gemini API key nếu muốn bật trả lời Gemini; chức năng SQL vẫn có fallback.
- Node.js không bắt buộc để chạy frontend.

## Cài đặt và chạy nhanh

Clone repository, tạo môi trường Python và cài dependencies:

```powershell
git clone https://github.com/manhtruong-web/smartmart-ai.git
cd smartmart-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Sau khi cập nhật cấu hình trong `backend/.env`, chạy backend từ thư mục gốc:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

Mở terminal thứ hai tại thư mục gốc để chạy frontend:

```powershell
python -m http.server 5500 --directory frontend
```

Truy cập `http://127.0.0.1:5500`; API mặc định ở `http://127.0.0.1:8000`.
Kiểm tra backend tại `http://127.0.0.1:8000/api/health`.

### Cấu hình database và Gemini

Trong `backend/.env`, đặt `DATABASE_URL` theo SQLAlchemy/pyodbc. Ví dụ trong
`.env.example` dùng ODBC Driver 17; thay `USER`, `PASSWORD` và `SERVER` bằng
giá trị riêng của môi trường. Mã hóa URL các ký tự đặc biệt trong thông tin đăng
nhập. Không commit file `backend/.env`.

Đặt `GEMINI_API_KEY` bằng key được cấp riêng. `GEMINI_MODEL` có thể được giữ ở
giá trị mẫu hoặc đặt theo model khả dụng cho tài khoản. Không cần OpenAI key.
`VISUAL_SEARCH_VISION_ENABLED` mặc định là `false`; bật chỉ khi chấp thuận gửi
ảnh đã resize tới Gemini Vision.

Tạo schema nền bằng `database/create_database.sql` trong SQL Server Management
Studio, sau đó chạy `database/migrations/002_product_recipes.sql` để cài bảng
công thức. Không có dữ liệu kinh doanh mẫu trong repository; kết nối database
được cấp quyền và nạp catalog riêng trước khi kiểm tra các chức năng sản phẩm.

Ảnh sản phẩm, dữ liệu catalog đã xuất, index FAISS, dataset, bản sao lưu database
và file `.env` không được đưa lên GitHub. Cần đặt ảnh sản phẩm có quyền sử dụng
trong `backend/static/Images/Products/` theo đường dẫn trong SQL Server; chỉ mục
ảnh có thể được tạo lại từ dữ liệu của môi trường triển khai.

### Chạy kiểm thử

```powershell
python -m unittest tests.test_core tests.test_api tests.test_recipes tests.test_visual_search -v
node --check frontend\app.js
```

### Xử lý lỗi thường gặp

- **Không kết nối được SQL Server:** kiểm tra dịch vụ/host, cổng, quyền tài khoản,
  ODBC Driver và định dạng `DATABASE_URL`.
- **Chatbot chỉ dùng câu trả lời dự phòng:** kiểm tra `GEMINI_API_KEY`, model và
  khả năng truy cập Google Gemini API; các truy vấn SQL vẫn có thể hoạt động.
- **Không thấy ảnh sản phẩm:** kiểm tra đường dẫn `SanPham.Anh`, file ảnh cục bộ
  và quyền đọc thư mục `backend/static`.
- **Frontend không gọi được API:** chạy cả hai server trên đúng cổng và kiểm tra
  lỗi trong Console của trình duyệt.

## Tạo index dataset (tùy chọn)

Từ thư mục gốc dự án:

```bash
chmod +x scripts/download_dataset.sh
./scripts/download_dataset.sh
python scripts/dataset_reader.py
```

Lệnh đọc sẽ báo số ảnh của `train`, `val`, `test` và số lớp trong `classes.csv`.
Mỗi dòng split chính thức có đường dẫn ảnh, nhãn fine-grained và nhãn coarse-grained.

Cài dependency backend rồi tạo index chỉ từ tập train:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python scripts/build_index.py
```

Mô hình ResNet18 pretrained được dùng để trích xuất vector 512 chiều, chuẩn hóa
L2 và lưu bằng `faiss.IndexFlatIP` (inner product tương đương cosine similarity
sau chuẩn hóa). Tập validation/test không được đưa vào index.

Đánh giá truy hồi trên tập test:

```bash
python scripts/evaluate.py
```

## Chạy FastAPI

Sao chép `backend/.env.example` thành `backend/.env`, điền `DATABASE_URL` và
`GEMINI_API_KEY` nếu muốn bật chatbot Gemini. Sau đó:

```bash
cd backend
uvicorn app.main:app --reload
```

Mở `frontend/index.html` bằng trình duyệt. Nếu trình duyệt chặn gọi API từ
file cục bộ, chạy `python -m http.server 5500 --directory frontend` rồi mở
`http://localhost:5500`.

### Hình ảnh sản phẩm

`dbo.SanPham.Anh` lưu đường dẫn tương đối trong thư mục `backend/static` (ví dụ
`Images/Products/sua-dutch-lady.jpg`). API danh sách và chi tiết trả trường
`Anh` dưới dạng `/api/products/{MaSP}/image`; endpoint này chỉ phục vụ JPG,
JPEG, PNG và WebP nằm trong thư mục ảnh cho phép. Dấu `/` và `\` đều được hỗ
trợ, còn đường dẫn ngoài thư mục bị từ chối. Ảnh hiển thị chỉ lấy từ đúng
đường dẫn file lưu cho sản phẩm trong SQL Server; nếu ảnh trống, không tồn tại
hoặc không hợp lệ, API trả placeholder và không thay bằng ảnh dataset. Dataset
không được dùng làm ảnh sản phẩm hoặc nguồn embedding thay thế. API trả
`X-Image-Source` là `product` hoặc `placeholder`; frontend gắn phiên bản vào URL
ảnh để tránh dùng lại ảnh cũ từ cache.

### Tìm kiếm sản phẩm bằng ảnh

Ảnh được kiểm tra và xem trước trong khung chat; chọn ảnh không gửi request.
Khách có thể gửi kèm câu hỏi hoặc chỉ gửi ảnh. Nếu API lỗi, ảnh và nội dung
được giữ lại để thử lại; chỉ xóa preview sau khi tìm kiếm thành công.

`POST /api/chat/search-by-image` đọc ảnh tải lên trong bộ nhớ, kiểm tra định dạng
JPG/JPEG/PNG/WebP, giới hạn dung lượng 8 MB, 20 megapixel và thu nhỏ ảnh đầu vào
trước khi suy luận. SQL Server vẫn là nguồn duy nhất về tên, danh mục, thương
hiệu, giá và tồn kho. Ảnh tải lên chỉ được xử lý trong bộ nhớ; ảnh sản phẩm được
lập chỉ mục phải resolve tới file thực trong `backend/static`. Không thay ảnh
SQL bằng ảnh dataset và không thay đổi bảng sản phẩm.

OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`) tạo embedding ảnh-văn bản 512 chiều.
FAISS kết hợp truy hồi ảnh, truy hồi văn bản sản phẩm và metadata; ResNet18 hiện
có được dùng làm tín hiệu hình ảnh phụ, không phải tiêu chí kết luận duy nhất.
Ứng viên phải đạt điểm liên quan kết hợp tối thiểu 0,30; ảnh tổng hợp không giống
sản phẩm đã bị loại trong kiểm thử hồi quy.
Cache tại `faiss_index/visual_product_embeddings.json` lưu embedding theo hash
nội dung ảnh, embedding metadata theo hash văn bản, dấu thời gian và lỗi xử lý.
Các ảnh trùng nội dung dùng chung một vector; nhiều ảnh cùng sản phẩm được đọc
từ `SanPham.Anh` và các đường dẫn ảnh hợp lệ trong `SanPhamAnh`. Giá và tồn kho
được đọc lại trực tiếp từ SQL Server khi trả kết quả.

Khi tìm thấy sản phẩm, backend gửi tối đa 10 kết quả đã xác thực từ SQL Server
cùng lịch sử liên quan và ý định hội thoại tới Gemini để tư vấn; Gemini không
thay thế bước tìm kiếm và không được tự tạo tên, giá hoặc tồn kho. Khi khách chọn
một sản phẩm, frontend ưu tiên mã sản phẩm đó cho các câu hỏi tiếp nối; giá và
tồn kho được truy vấn lại từ SQL Server.

Gemini Vision dùng cho OCR/nhận diện nhiều vật thể là tùy chọn và tắt mặc định.
Chỉ bật `VISUAL_SEARCH_VISION_ENABLED=true` nếu chấp thuận gửi ảnh đã resize tới
Google; không bật thì OpenCLIP, ResNet và metadata vẫn hoạt động cục bộ, nhưng
OCR/nhận diện vật thể riêng biệt có thể hạn chế hơn. Ảnh người dùng không được
lưu vào cache.

Sau khi cấu hình `ADMIN_API_TOKEN` trong `backend/.env` và khởi động lại backend,
mở `frontend/visual-search-admin.html`, nhập token rồi chọn **Quét toàn bộ sản
phẩm**. Dashboard và thao tác đồng bộ dùng token; chỉ mục được build theo batch
trong background. **Xử lý lại ảnh lỗi** giữ lại vector hợp lệ và thử lại các ảnh
thất bại. API phân trang tối đa 10 kết quả mỗi trang; lựa chọn và đánh giá hữu
ích được ghi thành telemetry không kèm ảnh hay nội dung truy vấn.

Kiểm thử tìm kiếm bao gồm ảnh catalog, ảnh nghiêng, ảnh ghép hai sản phẩm, nền
tổng hợp và ảnh không liên quan. Kiểm thử trên ảnh catalog gốc không đại diện
cho độ chính xác ngoài thực tế; cần tập ảnh truy vấn có nhãn riêng để đánh giá
góc chụp, ánh sáng, nền phức tạp và ảnh bị che.

### Danh mục và bộ lọc sản phẩm

Giao diện dùng sidebar để lọc danh mục, một hoặc nhiều thương hiệu, khoảng giá
và tình trạng tồn kho; có thể sắp xếp hoặc chuyển giữa dạng lưới và danh sách.
`GET /api/filters` trả tổng số sản phẩm, khoảng giá và số lượng theo danh mục/
thương hiệu trực tiếp từ SQL Server. Các bộ lọc được gửi tới
`GET /api/products/search`; tham số `brand` cũ vẫn được hỗ trợ, còn `brands`
có thể lặp lại để lọc nhiều thương hiệu. `out_of_stock_only=true` lọc sản phẩm
hết hàng.

### Chatbot hoàn chỉnh

Chatbot nhận diện các nhóm câu hỏi chào hỏi, giá, tồn kho, tìm theo ngân sách,
tìm kiếm và gợi ý. Các bộ lọc được chuyển thành truy vấn tham số hóa tới
SQL Server trước khi gọi Gemini. Gemini chỉ diễn đạt lại dữ liệu đã truy vấn;
nếu thiếu `GEMINI_API_KEY` hoặc API tạm lỗi, hệ thống dùng câu trả lời dự phòng
từ SQL Server và không tự tạo thông tin sản phẩm.

Ví dụ:

- `Sản phẩm này giá bao nhiêu?`
- `Có sữa còn hàng không?`
- `Gợi ý sản phẩm dưới 100.000 đồng`
- `Tư vấn sản phẩm phù hợp ngân sách 200k`

API `POST /api/chat` nhận:

```json
{
  "question": "Gợi ý sản phẩm dưới 100.000 đồng",
  "history": []
}
```

### Phân loại sản phẩm và tạo công thức

Recipe Generator đọc tên, danh mục, mô tả, thương hiệu và đơn vị tính từ
`dbo.SanPham`; không gửi giá bán hoặc tồn kho cho Gemini. Migration
`database/migrations/002_product_recipes.sql` chỉ bổ sung các bảng công thức và
phân loại, không sửa dữ liệu sản phẩm.

Đặt `GEMINI_API_KEY` và `DATABASE_URL` trong `backend/.env`, sau đó chạy từ thư
mục gốc để xem phạm vi hoặc xử lý theo lô:

```powershell
python scripts\generate_recipes.py --dry-run
python scripts\generate_recipes.py --batch-size 5
python scripts\generate_recipes.py --product-ids 81,165
```

Lệnh có thể tiếp tục sau lỗi từng sản phẩm; chạy lại sẽ bỏ qua dữ liệu đã xử lý
nếu thông tin sản phẩm không đổi. `--force` tạo lại kết quả đã xử lý. Nội dung
Gemini được lưu ở trạng thái `ai_generated`/`needs_review`, không phải nội dung
đã được nhà sản xuất xác nhận. Nguyên liệu chỉ liên kết tới sản phẩm thực có
trong catalog; nguyên liệu không tìm thấy được ghi là ngoài siêu thị. Sản phẩm
phi thực phẩm bị chặn khỏi việc tạo công thức. Có thể truy vấn công thức theo
mã sản phẩm qua `GET /api/products/{product_id}/recipes`.

Ảnh hiện trên thẻ công thức là ảnh sản phẩm/nguyên liệu trong catalog, không
phải ảnh minh họa món ăn do hệ thống tạo.

Mọi nội dung Gemini tạo đều là gợi ý tham khảo cần được duyệt; kết quả xử lý
phụ thuộc vào catalog trong database của từng môi trường.

## Cài đặt database

1. Mở SQL Server Management Studio hoặc Azure Data Studio.
2. Mở file `database/create_database.sql`.
3. Chạy toàn bộ script để tạo database và các bảng nền.
4. Chạy migration công thức nếu cần các API recipe:
   `database/migrations/002_product_recipes.sql`.
5. Nạp catalog từ nguồn được cấp phép và kiểm tra các bảng `DanhMuc`,
   `SanPham` và `SanPhamAnh`.

Chưa có dữ liệu giá bán hoặc tồn kho mẫu trong giai đoạn này. Những dữ liệu đó
phải được nhập từ nguồn kinh doanh thật của siêu thị, không lấy từ
`GroceryStoreDataset`.
