# Hướng dẫn sử dụng SmartMart AI

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
pip install -r backendequirements.txt
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
node --check frontendpp.js
```

## 10. Lưu ý
- Dữ liệu SQL, ảnh sản phẩm và API key không được đẩy lên GitHub.
- Một số tính năng nâng cao cần dữ liệu thực tế và môi trường kiểm thử riêng để đánh giá đầy đủ.
