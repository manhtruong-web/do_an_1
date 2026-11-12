# Import GroceryStoreDataset

Công cụ `import_grocery.py` chỉ tạo ánh xạ giữa nhãn Dataset và `SanPhamAnh`. Nó không tạo sản phẩm, không đặt giá, không đặt tồn kho và không sửa ảnh gốc.

## Mapping bắt buộc

Tạo CSV từ dữ liệu kinh doanh thật:

```csv
NhanDataset,MaSP
Golden-Delicious,123
Milk-Label,456
```

`MaSP` phải tồn tại và đang active trong `SmartMartAI.dbo.SanPham`. Không tự đoán mapping khi chưa chắc chắn.

## Dry-run

Từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe data_import\import_grocery.py --mapping data_import\product_label_map.csv
```

Lệnh trên chỉ thống kê candidate rows, không ghi SQL Server.

## Apply

Sau khi kiểm tra mapping:

```powershell
.\.venv\Scripts\python.exe data_import\import_grocery.py --mapping data_import\product_label_map.csv --apply
```

Script dùng `NOT EXISTS`, nên chạy lại không tạo mapping trùng. Có thể giới hạn split bằng `--split train`, `--split val`, hoặc `--split test`.

## Kiểm tra

```sql
SELECT COUNT(*) AS SoSanPham FROM dbo.SanPham;
SELECT COUNT(*) AS SoAnhMapping FROM dbo.SanPhamAnh;
SELECT TOP 20 MaSP, NhanDataset, DuongDanAnhDataset, TapDuLieu
FROM dbo.SanPhamAnh
ORDER BY MaAnh;
```
