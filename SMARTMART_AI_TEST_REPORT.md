# SMARTMART AI - TEST REPORT

Ngày kiểm tra: 2026-11-10

## 1. Tổng quan

SmartMart AI gồm frontend HTML/CSS/JavaScript thuần, backend FastAPI, SQL Server qua SQLAlchemy/pyodbc, OpenAI và FAISS với ResNet18 pretrained. Thư mục gốc là bản được kiểm tra; thư mục `smartmart-ai/` là bản sao và không được chỉnh sửa.

## 2. Trạng thái tổng hợp

| Hạng mục | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Backend FastAPI | PASS | Uvicorn startup thành công; `/api/health` trả 200 và `ok`. |
| Frontend | PASS | Static server trả `index.html` và `app.js` mã 200; JavaScript syntax hợp lệ. |
| Python/.venv/dependencies | PASS | `.venv` tồn tại; các thư viện chính import được; `pip check` không có lỗi. |
| SQL Server | PASS | Kết nối được `SmartMartAI`; không tái hiện Named Pipes/error 53. |
| Schema SQL | PASS | `DanhMuc`, `SanPham`, `SanPhamAnh` tồn tại với các cột phù hợp source. |
| Dữ liệu kinh doanh | BLOCKED | Ba bảng hiện có 0 bản ghi; không được tự tạo dữ liệu giả. |
| OpenAI API | BLOCKED | `.env` chỉ chứa placeholder `YOUR_API_KEY_THAT`; không có key hợp lệ để gọi model. |
| OpenAI fallback | PASS | Chatbot trả lời fallback từ SQL, không gọi OpenAI khi key là placeholder. |
| FAISS index | PASS | Index và metadata tồn tại; image search trả 5 kết quả thực tế. |
| FAISS evaluation | PASS | 2.485 ảnh test, top-1 accuracy `0.5988`. |
| Dataset mapping sang SQL | BLOCKED | Không có bản ghi `SanPham`/`SanPhamAnh` để xác nhận ánh xạ kinh doanh. |

## 3. Dataset thực tế

Đã chạy `scripts/dataset_report.py` và tạo `dataset_report.json`.

- Số class: 81.
- Train: 2.640 ảnh, 2.640 hợp lệ, 0 lỗi.
- Validation: 296 ảnh, 296 hợp lệ, 0 lỗi.
- Test: 2.485 ảnh, 2.485 hợp lệ, 0 lỗi.
- Tổng ảnh trong các split: 5.421.
- Tổng ảnh hợp lệ trong các split: 5.421.
- Tổng ảnh lỗi trong các split: 0.
- Ảnh quét đệ quy theo phần mở rộng: 5.502.
- Định dạng trong các split: JPEG.
- License file: có tại `dataset/GroceryStoreDataset/LICENSE`.

Dataset gốc không bị đổi tên, xóa hoặc sửa nội dung.

## 4. FAISS và model ảnh

- Model: ResNet18 pretrained từ torchvision.
- Vector được L2-normalize và truy hồi bằng inner product.
- Index: `faiss_index/products.index`.
- Metadata: `faiss_index/metadata.json`.
- Metadata hiện có 2.640 vector và 81 nhãn.
- `POST /api/image-search` với ảnh thật trong dataset trả HTTP 200, 5 matches và 0 sản phẩm SQL do bảng ánh xạ rỗng.
- `scripts/build_index.py` và `scripts/evaluate.py` đã được sửa để chạy đúng từ thư mục gốc.

## 5. SQL Server

Kết nối thực tế trả database `SmartMartAI`.

Các bảng và cột được kiểm tra:

- `dbo.DanhMuc`: `MaDM`, `TenDM`, `MoTa`, `TrangThai`.
- `dbo.SanPham`: `MaSP`, `MaDM`, `TenSP`, `MoTa`, `ThuongHieu`, `Anh`, `DonViTinh`, `GiaBan`, `SoLuongTon`, `HanSuDung`, `TrangThai`, `NgayTao`, `NgayCapNhat`.
- `dbo.SanPhamAnh`: `MaAnh`, `MaSP`, `DuongDanAnhDataset`, `NhanDataset`, `LaAnhDaiDien`, `TapDuLieu`, `NgayTao`.

Số lượng hiện tại:

- `DanhMuc`: 0.
- `SanPham`: 0.
- `SanPhamAnh`: 0.

## 5.1. Chẩn đoán lỗi tìm kiếm được báo cáo

Đã gọi lại chính xác các từ khóa `sữa`, `rau`, `Táo vàng Golden Delicious`, `sua` và `trái cây` qua `/api/products`; tất cả trả HTTP 200 nhưng 0 dòng vì ba bảng đích đang rỗng. Chatbot Python cũng nhận đủ cả năm câu với HTTP 200 và đúng intent `search`, nhưng không thể trả sản phẩm khi SQL không có bản ghi.

Đã thử thêm target `LAPTOP-KHJR6D25\\SQLEXPRESS` từng xuất hiện trong cấu hình mẫu bằng cùng thông tin cấu hình hiện có; target này cũng vào `SmartMartAI` với số dòng `0, 0, 0`. Không tự ý đổi `.env` hoặc chèn dữ liệu.

Các nguyên nhân code đã được xử lý:

- Chuẩn hóa chữ hoa/thường, dấu tiếng Việt và khoảng trắng.
- Dùng `COLLATE Vietnamese_CI_AI` cho tên, mô tả, thương hiệu và danh mục.
- Nhận diện `rau`, `trái cây`, `thịt`, `cá`, `đồ uống`, `bánh kẹo` như danh mục.
- Tách đúng tên nhiều từ như `Táo vàng Golden Delicious`.
- Giữ JOIN `SanPham.MaDM = DanhMuc.MaDM` và điều kiện sản phẩm active; không nới lỏng để tạo kết quả giả.

Không tạo, xóa hoặc thay đổi database/schema/dữ liệu.

## 6. Chatbot và truy vấn

Đã bổ sung và kiểm thử:

- Intent greeting, search, price, availability, budget, recommendation, comparison.
- Tiếng Việt có dấu và không dấu.
- Một số truy vấn tiếng Anh như `Show me milk products` và `Find similar products`.
- Từ khóa chung như `tôi`, `muốn`, `mua`, `giá`, `sản phẩm`, số tiền không còn bị dùng làm keyword sản phẩm.
- Alias Việt-Anh cho một số nhãn thực tế như milk/sữa, apple/táo, banana/chuối, tomato/cà chua, potato/khoai tây.
- Lọc `in_stock_only` và sắp xếp giá/tồn kho tăng hoặc giảm.
- Truy vấn dùng bind parameters; cột sort được giới hạn bằng allow-list.
- Placeholder OpenAI không còn kích hoạt request giả.

Do database rỗng, các câu hỏi sản phẩm trả về câu trả lời rõ ràng rằng chưa có dữ liệu, không bịa sản phẩm/giá/tồn kho.

## 7. API và frontend

Đã kiểm tra:

- `GET /api/health`: PASS, HTTP 200.
- `GET /api/products`: PASS, HTTP 200, trả `[]` khi database rỗng.
- `GET /api/products?category=milk&in_stock_only=true&sort_by=price&order=asc`: PASS, HTTP 200.
- `POST /api/chat`: PASS, HTTP 200; câu ngân sách nhận intent `budget`.
- `POST /api/image-search`: PASS với ảnh thật, HTTP 200, 5 kết quả FAISS.
- Upload `text/plain`: nhánh từ chối loại file được kiểm tra.
- Upload bytes không phải ảnh với MIME ảnh: nhánh ảnh không hợp lệ được kiểm tra.
- Frontend tải được HTML/JS qua static server.
- Frontend đã có trạng thái đang tìm/đang gửi, chống gửi trùng, hiển thị ảnh sản phẩm khi SQL có trường `Anh`, và escape nội dung chat.

## 8. OpenAI

- Model cấu hình: `gpt-4o-mini`.
- API key: BLOCKED vì giá trị hiện tại là placeholder, không phải secret hợp lệ.
- Không in key hoặc mật khẩu ra log.
- Khi key thật được cấu hình, client dùng timeout 15 giây và không retry vô hạn.
- Khi API lỗi, backend ghi loại exception đã rút gọn và trả fallback SQL.
- Chưa thể xác nhận model thật hoặc câu trả lời tiếng Việt từ OpenAI khi chưa có key hợp lệ.

## 9. Kiểm thử tự động

Đã thêm `tests/test_core.py` và chạy:

```text
Ran 3 tests in 0.006s
OK
```

Các test bao phủ intent tiếng Việt/không dấu/Anh, budget/comparison/similar và truy vấn SQL parameterized với sort an toàn.

## 10. File đã sửa hoặc tạo

- `backend/app/config.py`: đọc `.env` ổn định theo vị trí file, resolve dataset/FAISS path, nhận diện placeholder OpenAI.
- `backend/app/products.py`: alias tìm kiếm, lọc tồn kho, sort allow-list, sửa `ORDER BY` trùng cột.
- `backend/app/assistant.py`: nâng cấp intent, từ khóa, ngân sách, fallback và timeout OpenAI.
- `backend/app/main.py`: thêm tham số lọc tồn kho và sắp xếp cho `/api/products`.
- `frontend/app.js`: loading state, chống gửi trùng, ảnh sản phẩm, xử lý lỗi và escape text.
- `frontend/index.html`: aria-live cho trạng thái ảnh/chat.
- `frontend/style.css`: kiểu hiển thị ảnh sản phẩm.
- `scripts/build_index.py`: chạy độc lập từ project root.
- `scripts/evaluate.py`: chạy độc lập từ project root.
- `scripts/dataset_report.py`: công cụ tạo báo cáo dataset tái lập được.
- `tests/test_core.py`: kiểm thử tự động lõi.
- `dataset_report.json`: số liệu dataset thực tế.

## 11. Hạn chế còn lại

1. Cần người dùng cung cấp OpenAI API key hợp lệ trong `backend/.env` để kiểm thử gọi model thật.
2. Cần người dùng nạp dữ liệu kinh doanh thật vào SQL Server để xác nhận `/api/products`, tư vấn giá/tồn kho và ánh xạ ảnh sang sản phẩm.
3. Không tự tạo dữ liệu mẫu vì master prompt cấm làm sai lệch dữ liệu kinh doanh.
4. Accuracy `0.5988` là top-1 retrieval theo nhãn fine-grained của dataset, chưa phải precision/recall nghiệp vụ do chưa có mapping SQL.
5. `TestClient` phát cảnh báo tương thích `httpx` của môi trường hiện tại; không ảnh hưởng runtime FastAPI. 
