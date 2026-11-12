import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    print("--- TABLES ---")
    tables = conn.execute(text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")).fetchall()
    for t in tables:
        print("Table:", t[0])

    print("\n--- COLUMNS IN SanPham ---")
    cols = conn.execute(text("SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SanPham'")).fetchall()
    for col in cols:
        print(f"  {col[0]}: {col[1]} ({col[2]})")

    print("\n--- SAMPLE SAN PHAM ---")
    rows = conn.execute(text("SELECT TOP 5 MaSP, TenSP, Anh, DonViTinh, GiaBan, SoLuongTon FROM SanPham")).fetchall()
    for r in rows:
        print(dict(r._mapping))

    # Check SanPhamAnh if exists
    if any(t[0] == 'SanPhamAnh' for t in tables):
        print("\n--- COLUMNS IN SanPhamAnh ---")
        cols = conn.execute(text("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SanPhamAnh'")).fetchall()
        for col in cols:
            print(f"  {col[0]}: {col[1]}")
        count_spa = conn.execute(text("SELECT COUNT(*) FROM SanPhamAnh")).scalar()
        print("Count SanPhamAnh:", count_spa)
        sample_spa = conn.execute(text("SELECT TOP 5 * FROM SanPhamAnh")).fetchall()
        for r in sample_spa:
            print(dict(r._mapping))

    # Check any other tables
    for tbl in ['HoiThoai', 'TinNhan', 'KnowledgeItem']:
        if any(t[0].lower() == tbl.lower() for t in tables):
            print(f"\n--- {tbl} exists ---")
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            print(f"Count {tbl}:", cnt)
