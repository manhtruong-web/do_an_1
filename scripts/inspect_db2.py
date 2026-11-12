import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    tables = [
        'AI_ProductEmbedding', 'AI_Conversation', 'AI_ChatMessage',
        'AI_ConversationSummary', 'AI_ProductAlias', 'AI_SearchLog'
    ]
    for tbl in tables:
        print(f"\n--- COLUMNS IN {tbl} ---")
        cols = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tbl}'")).fetchall()
        for col in cols:
            print(f"  {col[0]}: {col[1]} ({col[2]})")
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        print(f"Count {tbl}:", cnt)

    # Check SanPham: what kinds of values are in column Anh?
    print("\n--- SAMPLE VALUES IN SanPham.Anh ---")
    anh_samples = conn.execute(text("SELECT TOP 20 MaSP, TenSP, Anh FROM SanPham")).fetchall()
    for s in anh_samples:
        print(f"MaSP={s[0]}: {s[1]} -> Anh='{s[2]}'")
