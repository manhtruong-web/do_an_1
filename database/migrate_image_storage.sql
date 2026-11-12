/*
    SmartMart AI - Migration: Lưu trữ hình ảnh sản phẩm trực tiếp trong SQL Server
    Mục tiêu:
    - Loại bỏ phụ thuộc vào hình ảnh bên ngoài/GitHub.
    - Bổ sung cột HinhAnh VARBINARY(MAX) vào dbo.SanPham để lưu trữ byte ảnh gốc.
    - Tạo bảng dbo.AI_ProductImageEmbedding để cache vector đặc trưng phục vụ Image Similarity Search.
    - Giữ toàn vẹn dữ liệu kinh doanh hiện tại (giá, tồn kho, danh mục).
*/

USE SmartMartAI;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

-- 1. Bổ sung cột HinhAnh VARBINARY(MAX) vào dbo.SanPham nếu chưa tồn tại
IF NOT EXISTS (
    SELECT 1 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = 'dbo' 
      AND TABLE_NAME = 'SanPham' 
      AND COLUMN_NAME = 'HinhAnh'
)
BEGIN
    ALTER TABLE dbo.SanPham ADD HinhAnh VARBINARY(MAX) NULL;
    PRINT N'Đã thêm cột HinhAnh VARBINARY(MAX) vào bảng dbo.SanPham.';
END
ELSE
BEGIN
    PRINT N'Cột HinhAnh đã tồn tại trong bảng dbo.SanPham.';
END
GO

-- 2. Tạo bảng lưu trữ vector đặc trưng ảnh AI_ProductImageEmbedding
IF OBJECT_ID(N'dbo.AI_ProductImageEmbedding', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AI_ProductImageEmbedding
    (
        MaSP INT NOT NULL,
        EmbeddingJson NVARCHAR(MAX) NOT NULL,
        Dimensions INT NOT NULL DEFAULT 512,
        ModelName NVARCHAR(100) NOT NULL DEFAULT N'ResNet18-L2Norm',
        ContentHash VARCHAR(64) NOT NULL,
        UpdatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_AI_ProductImageEmbedding_UpdatedAt DEFAULT SYSDATETIME(),

        CONSTRAINT PK_AI_ProductImageEmbedding PRIMARY KEY (MaSP),
        CONSTRAINT FK_AI_ProductImageEmbedding_SanPham FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP) ON DELETE CASCADE
    );
    PRINT N'Đã tạo bảng dbo.AI_ProductImageEmbedding.';
END
ELSE
BEGIN
    PRINT N'Bảng dbo.AI_ProductImageEmbedding đã tồn tại.';
END
GO

-- 3. Tạo bảng lưu trữ ảnh mặc định của hệ thống
IF OBJECT_ID(N'dbo.SystemDefaultImage', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SystemDefaultImage
    (
        ImageKey NVARCHAR(50) NOT NULL PRIMARY KEY,
        ImageData VARBINARY(MAX) NOT NULL,
        MimeType NVARCHAR(50) NOT NULL DEFAULT N'image/svg+xml',
        Description NVARCHAR(250) NULL,
        UpdatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_SystemDefaultImage_UpdatedAt DEFAULT SYSDATETIME()
    );
    PRINT N'Đã tạo bảng dbo.SystemDefaultImage.';
END
ELSE
BEGIN
    PRINT N'Bảng dbo.SystemDefaultImage đã tồn tại.';
END
GO
