
print("BAT DAU KIEM TRA SQL SERVER")

import pyodbc

print("Da import pyodbc")

try:
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LAPTOP-KHJR6D25\\SQLEXPRESS;"
    "DATABASE=SmartMartAI;"
    "UID=sa;"
    "PWD=123;"
    "TrustServerCertificate=yes;",
        timeout=5
    )

    print("KET NOI SQL SERVER THANH CONG!")

    cursor = conn.cursor()
    cursor.execute("SELECT DB_NAME(), SYSTEM_USER")

    result = cursor.fetchone()

    print("Database:", result[0])
    print("Tai khoan:", result[1])

    cursor.execute("SELECT name FROM sys.tables")

    print("Danh sach bang:")
    for row in cursor.fetchall():
        print(row[0])

    conn.close()

except Exception as e:
    print("KET NOI THAT BAI!")
    print(repr(e))

print("KET THUC KIEM TRA")
