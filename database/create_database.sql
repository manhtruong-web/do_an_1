/*
    SmartMart AI - Giai đoạn 1
    Thiết kế cơ sở dữ liệu SQL Server

    Lưu ý:
    - GroceryStoreDataset chỉ dùng cho nhận diện/tìm kiếm ảnh.
    - Không đưa giá bán, tồn kho hoặc hạn sử dụng giả định vào dataset.
    - Các thông tin kinh doanh phải được quản lý trong cơ sở dữ liệu này.
*/

USE [master];
GO
USE master;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.server_principals
    WHERE name = N'LAPTOP-KHJR6D25\TRUONG'
)
BEGIN
    CREATE LOGIN [LAPTOP-KHJR6D25\TRUONG]
    FROM WINDOWS;
END
GO

USE SmartMartAI;
GO




IF DB_ID(N'SmartMartAI') IS NULL
BEGIN
    CREATE DATABASE SmartMartAI;
END;
GO

USE SmartMartAI;
GO

IF OBJECT_ID(N'dbo.DanhMuc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DanhMuc
    (
        MaDM INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_DanhMuc PRIMARY KEY,
        TenDM NVARCHAR(150) NOT NULL
            CONSTRAINT UQ_DanhMuc_TenDM UNIQUE,
        MoTa NVARCHAR(500) NULL,
        TrangThai BIT NOT NULL
            CONSTRAINT DF_DanhMuc_TrangThai DEFAULT (1)
    );
END;
GO

IF OBJECT_ID(N'dbo.SanPham', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SanPham
    (
        MaSP INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_SanPham PRIMARY KEY,
        MaDM INT NOT NULL,
        TenSP NVARCHAR(250) NOT NULL,
        MoTa NVARCHAR(1000) NULL,
        ThuongHieu NVARCHAR(150) NULL,
        Anh NVARCHAR(500) NULL,
        DonViTinh NVARCHAR(50) NOT NULL,
        GiaBan DECIMAL(18,2) NOT NULL,
        SoLuongTon INT NOT NULL
            CONSTRAINT DF_SanPham_SoLuongTon DEFAULT (0),
        HanSuDung DATE NULL,
        TrangThai BIT NOT NULL
            CONSTRAINT DF_SanPham_TrangThai DEFAULT (1),
        NgayTao DATETIME2(0) NOT NULL
            CONSTRAINT DF_SanPham_NgayTao DEFAULT (SYSDATETIME()),
        NgayCapNhat DATETIME2(0) NOT NULL
            CONSTRAINT DF_SanPham_NgayCapNhat DEFAULT (SYSDATETIME()),

        CONSTRAINT FK_SanPham_DanhMuc
            FOREIGN KEY (MaDM) REFERENCES dbo.DanhMuc(MaDM),
        CONSTRAINT CK_SanPham_GiaBan
            CHECK (GiaBan >= 0),
        CONSTRAINT CK_SanPham_SoLuongTon
            CHECK (SoLuongTon >= 0)
    );
END;
GO

IF OBJECT_ID(N'dbo.SanPhamAnh', N'U') IS NULL
BEGIN
    /*
        Bảng ánh xạ giữa sản phẩm trong SQL Server và ảnh/nhãn của
        GroceryStoreDataset. DuongDanAnhDataset không chứa giá hoặc tồn kho.
    */
    CREATE TABLE dbo.SanPhamAnh
    (
        MaAnh INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_SanPhamAnh PRIMARY KEY,
        MaSP INT NOT NULL,
        DuongDanAnhDataset NVARCHAR(1000) NOT NULL,
        NhanDataset NVARCHAR(250) NOT NULL,
        LaAnhDaiDien BIT NOT NULL
            CONSTRAINT DF_SanPhamAnh_LaAnhDaiDien DEFAULT (0),
        TapDuLieu NVARCHAR(20) NOT NULL,
        NgayTao DATETIME2(0) NOT NULL
            CONSTRAINT DF_SanPhamAnh_NgayTao DEFAULT (SYSDATETIME()),

        CONSTRAINT FK_SanPhamAnh_SanPham
            FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP),
        CONSTRAINT CK_SanPhamAnh_TapDuLieu
            CHECK (TapDuLieu IN (N'train', N'val', N'test'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPham_MaDM'
                AND object_id = OBJECT_ID(N'dbo.SanPham'))
BEGIN
    CREATE INDEX IX_SanPham_MaDM ON dbo.SanPham(MaDM);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPham_TenSP'
                AND object_id = OBJECT_ID(N'dbo.SanPham'))
BEGIN
    CREATE INDEX IX_SanPham_TenSP ON dbo.SanPham(TenSP);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPham_ThuongHieu'
                AND object_id = OBJECT_ID(N'dbo.SanPham'))
BEGIN
    CREATE INDEX IX_SanPham_ThuongHieu ON dbo.SanPham(ThuongHieu);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPham_GiaBan_TrangThai'
                AND object_id = OBJECT_ID(N'dbo.SanPham'))
BEGIN
    CREATE INDEX IX_SanPham_GiaBan_TrangThai
        ON dbo.SanPham(GiaBan, TrangThai);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPhamAnh_NhanDataset'
                AND object_id = OBJECT_ID(N'dbo.SanPhamAnh'))
BEGIN
    CREATE INDEX IX_SanPhamAnh_NhanDataset
        ON dbo.SanPhamAnh(NhanDataset);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = N'IX_SanPhamAnh_MaSP'
                AND object_id = OBJECT_ID(N'dbo.SanPhamAnh'))
BEGIN
    CREATE INDEX IX_SanPhamAnh_MaSP ON dbo.SanPhamAnh(MaSP);
END;
GO
select * from dbo.SanPham


-- 50 SAN PHAM CO SO: TEN TIENG VIET
USE SmartMartAI;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    INSERT INTO dbo.DanhMuc (TenDM, MoTa)
    SELECT v.TenDM, v.MoTa
    FROM (VALUES
        (N'Sữa và chế phẩm từ sữa', N'Sữa tươi, sữa đặc, sữa chua, phô mai và các sản phẩm từ sữa.'),
        (N'Đồ uống', N'Nước suối, nước ngọt, trà, cà phê và nước trái cây.'),
        (N'Rau củ', N'Các loại rau xanh và củ quả tươi.'),
        (N'Trái cây', N'Trái cây tươi trong nước và nhập khẩu.'),
        (N'Thịt và thủy sản', N'Thịt heo, bò, gà, cá và hải sản.'),
        (N'Bánh kẹo', N'Bánh quy, bánh ngọt, kẹo và đồ ăn vặt.'),
        (N'Gia vị', N'Nước mắm, nước tương, dầu ăn và gia vị nấu ăn.'),
        (N'Thực phẩm khô', N'Gạo, mì, bún, miến, ngũ cốc và các loại đậu.'),
        (N'Hóa mỹ phẩm', N'Sản phẩm chăm sóc cá nhân và vệ sinh nhà cửa.'),
        (N'Đồ gia dụng', N'Các vật dụng tiện ích sử dụng trong gia đình.')
    ) AS v(TenDM, MoTa)
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.DanhMuc d
        WHERE d.TenDM = v.TenDM
    );

    -- 2. Thêm 200 sản phẩm
        INSERT INTO dbo.SanPham
    (
        MaDM,
        TenSP,
        MoTa,
        ThuongHieu,
        Anh,
        DonViTinh,
        GiaBan,
        SoLuongTon,
        HanSuDung
    )
    SELECT
        dm.MaDM,
        p.TenSP,
        p.MoTa,
        p.ThuongHieu,
        p.Anh,
        p.DonViTinh,
        p.GiaBan,
        p.SoLuongTon,
        CASE
            WHEN p.SoNgayHan IS NULL THEN NULL
            ELSE DATEADD(DAY, p.SoNgayHan, CONVERT(DATE, GETDATE()))
        END
    FROM
    (
        VALUES

        -- =====================================
        -- 1. SỮA VÀ CHẾ PHẨM TỪ SỮA (20 SP)
        -- =====================================

        (1,N'Sữa tươi Vinamilk có đường 1L',N'Sữa tươi tiệt trùng có đường, hộp 1 lít.',N'Vinamilk',N'Images/Products/sua-tuoi-vinamilk-co-duong.jpg',N'Hộp',36000,50,180),
        (1,N'Sữa tươi Vinamilk không đường 1L',N'Sữa tươi tiệt trùng không đường.',N'Vinamilk',N'Images/Products/sua-tuoi-vinamilk-khong-duong.jpg',N'Hộp',35000,45,180),
        (1,N'Sữa tươi TH true MILK 1L',N'Sữa tươi nguyên chất tiệt trùng.',N'TH true MILK',N'Images/Products/sua-th.jpg',N'Hộp',39000,40,180),
        (1,N'Sữa tươi Dutch Lady 180ml',N'Sữa tươi hộp nhỏ tiện lợi.',N'Dutch Lady',N'Images/Products/sua-dutch-lady.jpg',N'Hộp',8500,100,150),
        (1,N'Sữa đặc Ông Thọ 380g',N'Sữa đặc có đường dùng pha chế và nấu ăn.',N'Ông Thọ',N'Images/Products/sua-dac-ong-tho.jpg',N'Lon',28000,60,365),
        (1,N'Sữa bột Dielac 400g',N'Sữa bột dinh dưỡng đóng hộp.',N'Vinamilk',N'Images/Products/sua-bot-dielac.jpg',N'Lon',145000,25,540),
        (1,N'Sữa đậu nành Fami 200ml',N'Sữa đậu nành đóng hộp uống liền.',N'Fami',N'Images/Products/sua-fami.jpg',N'Hộp',7000,100,180),
        (1,N'Sữa cacao Milo 180ml',N'Thức uống dinh dưỡng hương cacao.',N'Milo',N'Images/Products/sua-milo.jpg',N'Hộp',9000,80,180),
        (1,N'Sữa chua Vinamilk có đường',N'Sữa chua ăn vị truyền thống.',N'Vinamilk',N'Images/Products/sua-chua-vinamilk.jpg',N'Hũ',6000,100,25),
        (1,N'Sữa chua nha đam',N'Sữa chua kết hợp nha đam.',N'Vinamilk',N'Images/Products/sua-chua-nha-dam.jpg',N'Hũ',7000,80,25),
        (1,N'Sữa chua uống Yakult',N'Sữa uống lên men đóng chai nhỏ.',N'Yakult',N'Images/Products/yakult.jpg',N'Chai',6500,100,30),
        (1,N'Sữa chua uống TH true YOGURT',N'Sữa chua uống hương trái cây.',N'TH true YOGURT',N'Images/Products/sua-chua-uong-th.jpg',N'Chai',9000,70,45),
        (1,N'Phô mai Con Bò Cười',N'Phô mai mềm dạng miếng tam giác.',N'Con Bò Cười',N'Images/Products/pho-mai-con-bo-cuoi.jpg',N'Hộp',39000,30,150),
        (1,N'Phô mai lát cheddar',N'Phô mai lát dùng kẹp bánh mì.',N'Anchor',N'Images/Products/pho-mai-lat.jpg',N'Gói',42000,25,120),
        (1,N'Bơ lạt Anchor 200g',N'Bơ lạt dùng làm bánh và nấu ăn.',N'Anchor',N'Images/Products/bo-lat-anchor.jpg',N'Hộp',68000,20,120),
        (1,N'Sữa hạt óc chó 1L',N'Thức uống hạt óc chó đóng hộp.',N'TH true NUT',N'Images/Products/sua-hat-oc-cho.jpg',N'Hộp',42000,30,180),
        (1,N'Sữa tươi organic 1L',N'Sữa tươi hữu cơ nguyên chất.',N'TH true MILK',N'Images/Products/sua-organic.jpg',N'Hộp',49000,20,150),
        (1,N'Sữa ít béo Devondale 1L',N'Sữa tươi ít béo đóng hộp.',N'Devondale',N'Images/Products/sua-devondale.jpg',N'Hộp',59000,15,180),
        (1,N'Kem vani Merino 450ml',N'Kem vani dùng làm món tráng miệng.',N'Merino',N'Images/Products/kem-merino.jpg',N'Hộp',52000,25,180),
        (1,N'Sữa bắp Nuti 180ml',N'Thức uống từ bắp thơm ngọt.',N'Nuti',N'Images/Products/sua-bap.jpg',N'Hộp',8000,60,150),

        -- =====================================
        -- 2. ĐỒ UỐNG (20 SP)
        -- =====================================

        (2,N'Nước suối Aquafina 500ml',N'Nước uống tinh khiết đóng chai.',N'Aquafina',N'Images/Products/aquafina.jpg',N'Chai',6000,150,730),
        (2,N'Nước khoáng La Vie 500ml',N'Nước khoáng thiên nhiên đóng chai.',N'La Vie',N'Images/Products/lavie.jpg',N'Chai',7000,130,730),
        (2,N'Nước suối Dasani 1.5L',N'Nước tinh khiết chai lớn.',N'Dasani',N'Images/Products/dasani.jpg',N'Chai',10000,90,730),
        (2,N'Nước cam Twister 1L',N'Nước giải khát hương cam.',N'Twister',N'Images/Products/twister.jpg',N'Hộp',32000,40,180),
        (2,N'Nước táo Minute Maid 1L',N'Nước ép táo đóng hộp.',N'Minute Maid',N'Images/Products/minute-maid.jpg',N'Hộp',30000,35,180),
        (2,N'Trà xanh Không Độ 455ml',N'Trà xanh đóng chai uống liền.',N'Không Độ',N'Images/Products/tra-khong-do.jpg',N'Chai',10000,100,180),
        (2,N'Trà ô long Tea Plus',N'Trà ô long đóng chai.',N'Tea Plus',N'Images/Products/tea-plus.jpg',N'Chai',10000,85,180),
        (2,N'Trà đào C2',N'Trà đào hương trái cây.',N'C2',N'Images/Products/c2.jpg',N'Chai',9000,90,180),
        (2,N'Nước tăng lực Red Bull',N'Nước uống tăng lực đóng lon.',N'Red Bull',N'Images/Products/redbull.jpg',N'Lon',12000,80,365),
        (2,N'Nước tăng lực Sting',N'Nước tăng lực hương dâu.',N'Sting',N'Images/Products/sting.jpg',N'Lon',11000,75,365),
        (2,N'Coca-Cola lon 330ml',N'Nước giải khát có gas vị cola.',N'Coca-Cola',N'Images/Products/cocacola.jpg',N'Lon',10000,120,365),
        (2,N'Mirinda cam 330ml',N'Nước ngọt có gas vị cam.',N'Mirinda',N'Images/Products/mirinda.jpg',N'Lon',10000,90,365),
        (2,N'Sprite chanh 330ml',N'Nước giải khát có gas vị chanh.',N'Sprite',N'Images/Products/sprite.jpg',N'Lon',10000,90,365),
        (2,N'7UP 330ml',N'Nước giải khát có gas.',N'7UP',N'Images/Products/7up.jpg',N'Lon',10000,85,365),
        (2,N'Cà phê sữa Birdy',N'Cà phê sữa uống liền.',N'Birdy',N'Images/Products/birdy.jpg',N'Lon',12000,70,270),
        (2,N'Cà phê đen Nescafe',N'Cà phê đen đóng lon.',N'Nescafe',N'Images/Products/nescafe.jpg',N'Lon',11000,65,270),
        (2,N'Cà phê hòa tan G7',N'Cà phê hòa tan 3 trong 1.',N'G7',N'Images/Products/g7.jpg',N'Hộp',65000,40,540),
        (2,N'Trà túi lọc Atiso',N'Trà atiso dùng pha nóng.',N'Đà Lạt',N'Images/Products/tra-atiso.jpg',N'Hộp',38000,25,540),
        (2,N'Nước dừa Vita Coco',N'Nước dừa đóng hộp tiện lợi.',N'Vita Coco',N'Images/Products/vita-coco.jpg',N'Hộp',22000,30,365),
        (2,N'Nước yến Sanest',N'Thức uống yến ngân nhĩ.',N'Sanest',N'Images/Products/sanest.jpg',N'Chai',18000,40,365),

        -- =====================================
        -- 3. RAU CỦ (20 SP)
        -- =====================================

        (3,N'Rau cải ngọt',N'Rau cải ngọt tươi dùng xào và nấu canh.',N'Nông sản Việt',N'Images/Products/cai-ngot.jpg',N'Kg',28000,35,5),
        (3,N'Cải thìa',N'Cải thìa tươi dùng xào và nấu canh.',N'Nông sản Việt',N'Images/Products/cai-thia.jpg',N'Kg',30000,28,5),
        (3,N'Rau muống',N'Rau muống tươi dùng luộc hoặc xào.',N'Nông sản Việt',N'Images/Products/rau-muong.jpg',N'Bó',12000,45,3),
        (3,N'Rau mồng tơi',N'Rau mồng tơi tươi dùng nấu canh.',N'Nông sản Việt',N'Images/Products/mong-toi.jpg',N'Bó',10000,30,3),
        (3,N'Xà lách xanh',N'Xà lách tươi dùng ăn sống và làm salad.',N'Đà Lạt',N'Images/Products/xa-lach.jpg',N'Kg',35000,20,5),
        (3,N'Bắp cải trắng',N'Bắp cải tươi dùng luộc và xào.',N'Nông sản Việt',N'Images/Products/bap-cai.jpg',N'Kg',22000,32,10),
        (3,N'Súp lơ xanh',N'Bông cải xanh tươi.',N'Đà Lạt',N'Images/Products/sup-lo.jpg',N'Kg',48000,18,7),
        (3,N'Cà rốt',N'Cà rốt tươi dùng nấu canh và xào.',N'Nông sản Việt',N'Images/Products/ca-rot.jpg',N'Kg',25000,40,14),
        (3,N'Khoai tây',N'Khoai tây tươi dùng chiên và chế biến.',N'Nông sản Việt',N'Images/Products/khoai-tay.jpg',N'Kg',26000,38,20),
        (3,N'Cà chua',N'Cà chua chín đỏ dùng nấu ăn.',N'Nông sản Việt',N'Images/Products/ca-chua.jpg',N'Kg',30000,34,7),
        (3,N'Dưa leo',N'Dưa leo tươi dùng ăn sống và làm salad.',N'Nông sản Việt',N'Images/Products/dua-leo.jpg',N'Kg',18000,40,7),
        (3,N'Hành tây',N'Hành tây củ dùng tạo vị thơm cho món ăn.',N'Nông sản Việt',N'Images/Products/hanh-tay.jpg',N'Kg',28000,25,20),
        (3,N'Hành tím',N'Hành tím khô dùng làm gia vị.',N'Nông sản Việt',N'Images/Products/hanh-tim.jpg',N'Kg',55000,20,60),
        (3,N'Tỏi khô',N'Tỏi củ dùng làm gia vị chế biến món ăn.',N'Nông sản Việt',N'Images/Products/toi.jpg',N'Kg',65000,18,90),
        (3,N'Ớt đỏ',N'Ớt đỏ tươi tạo vị cay cho món ăn.',N'Nông sản Việt',N'Images/Products/ot-do.jpg',N'Kg',45000,12,7),
        (3,N'Bí đỏ',N'Bí đỏ tươi dùng nấu canh và hấp.',N'Nông sản Việt',N'Images/Products/bi-do.jpg',N'Kg',22000,25,14),
        (3,N'Bí xanh',N'Bí xanh tươi dùng nấu canh.',N'Nông sản Việt',N'Images/Products/bi-xanh.jpg',N'Kg',20000,22,10),
        (3,N'Đậu que',N'Đậu que tươi dùng xào và luộc.',N'Nông sản Việt',N'Images/Products/dau-que.jpg',N'Kg',32000,20,5),
        (3,N'Nấm kim châm',N'Nấm kim châm dùng nấu lẩu và xào.',N'K-Food',N'Images/Products/nam-kim-cham.jpg',N'Gói',15000,30,10),
        (3,N'Ngô ngọt',N'Ngô ngọt tươi dùng luộc hoặc nấu súp.',N'Nông sản Việt',N'Images/Products/ngo-ngot.jpg',N'Bắp',10000,35,7),

        -- =====================================
        -- 4. TRÁI CÂY (20 SP)
        -- =====================================

        (4,N'Táo đỏ Mỹ',N'Táo đỏ giòn ngọt nhập khẩu từ Mỹ.',N'Washington',N'Images/Products/tao-do-my.jpg',N'Kg',89000,25,30),
        (4,N'Táo xanh Mỹ',N'Táo xanh vị chua nhẹ, giòn.',N'Mỹ',N'Images/Products/tao-xanh.jpg',N'Kg',95000,18,30),
        (4,N'Táo vàng',N'Táo vàng vị ngọt dịu.',N'Mỹ',N'Images/Products/tao-vang.jpg',N'Kg',99000,15,25),
        (4,N'Chuối già Nam Mỹ',N'Chuối già chín tự nhiên.',N'Dole',N'Images/Products/chuoi-gia.jpg',N'Kg',32000,30,7),
        (4,N'Chuối cau',N'Chuối cau nhỏ, vị ngọt thơm.',N'Việt Nam',N'Images/Products/chuoi-cau.jpg',N'Kg',28000,28,5),
        (4,N'Cam sành',N'Cam sành mọng nước.',N'Miền Tây',N'Images/Products/cam-sanh.jpg',N'Kg',35000,32,10),
        (4,N'Cam vàng Ai Cập',N'Cam vàng nhập khẩu, vị ngọt thanh.',N'Ai Cập',N'Images/Products/cam-vang.jpg',N'Kg',65000,20,20),
        (4,N'Quýt đường',N'Quýt đường vỏ mỏng, vị ngọt.',N'Miền Tây',N'Images/Products/quyt-duong.jpg',N'Kg',42000,25,10),
        (4,N'Nho xanh không hạt',N'Nho xanh giòn ngọt, không hạt.',N'Úc',N'Images/Products/nho-xanh.jpg',N'Kg',145000,12,14),
        (4,N'Nho đỏ không hạt',N'Nho đỏ ngọt, dùng ăn tráng miệng.',N'Mỹ',N'Images/Products/nho-do.jpg',N'Kg',135000,14,14),
        (4,N'Dưa hấu ruột đỏ',N'Dưa hấu ruột đỏ mọng nước.',N'Long An',N'Images/Products/dua-hau.jpg',N'Kg',18000,40,10),
        (4,N'Dưa lưới',N'Dưa lưới thơm ngọt, ruột màu cam.',N'Việt Nam',N'Images/Products/dua-luoi.jpg',N'Kg',55000,15,10),
        (4,N'Xoài cát Hòa Lộc',N'Xoài cát thơm ngọt.',N'Tiền Giang',N'Images/Products/xoai-cat.jpg',N'Kg',65000,20,7),
        (4,N'Xoài keo',N'Xoài keo giòn, phù hợp ăn xanh.',N'Campuchia',N'Images/Products/xoai-keo.jpg',N'Kg',35000,25,7),
        (4,N'Thanh long ruột đỏ',N'Thanh long ruột đỏ vị ngọt thanh.',N'Bình Thuận',N'Images/Products/thanh-long.jpg',N'Kg',38000,24,10),
        (4,N'Lê Hàn Quốc',N'Lê Hàn Quốc giòn mọng nước.',N'Hàn Quốc',N'Images/Products/le-han-quoc.jpg',N'Kg',89000,16,20),
        (4,N'Kiwi xanh',N'Kiwi xanh vị chua ngọt.',N'New Zealand',N'Images/Products/kiwi.jpg',N'Kg',160000,10,20),
        (4,N'Dâu tây Đà Lạt',N'Dâu tây tươi vị chua ngọt tự nhiên.',N'Đà Lạt',N'Images/Products/dau-tay.jpg',N'Hộp',65000,18,5),
        (4,N'Bơ sáp',N'Bơ sáp dẻo béo.',N'Đắk Lắk',N'Images/Products/bo-sap.jpg',N'Kg',55000,20,7),
        (4,N'Ổi lê',N'Ổi lê giòn ngọt.',N'Việt Nam',N'Images/Products/oi-le.jpg',N'Kg',28000,30,7),

        -- =====================================
        -- 5. THỊT VÀ THỦY SẢN (20 SP)
        -- =====================================

        (5,N'Thịt heo ba chỉ',N'Thịt ba chỉ heo tươi có tỷ lệ nạc mỡ cân đối.',N'Vissan',N'Images/Products/thit-ba-chi.jpg',N'Kg',165000,15,3),
        (5,N'Thịt heo nạc vai',N'Thịt nạc vai dùng kho và xay.',N'Vissan',N'Images/Products/thit-nac-vai.jpg',N'Kg',145000,18,3),
        (5,N'Thịt heo thăn',N'Thịt thăn heo ít mỡ.',N'Vissan',N'Images/Products/thit-than.jpg',N'Kg',155000,12,3),
        (5,N'Sườn non heo',N'Sườn non tươi dùng nấu canh và rim.',N'Vissan',N'Images/Products/suon-non.jpg',N'Kg',185000,10,3),
        (5,N'Thịt bò thăn',N'Thịt bò thăn mềm, phù hợp áp chảo.',N'MeatDeli',N'Images/Products/bo-than.jpg',N'Kg',320000,8,3),
        (5,N'Thịt bò xay',N'Thịt bò xay dùng làm sốt và viên thịt.',N'MeatDeli',N'Images/Products/bo-xay.jpg',N'Kg',220000,10,2),
        (5,N'Ức gà phi lê',N'Ức gà bỏ xương, dùng chế biến món ăn.',N'CP',N'Images/Products/uc-ga.jpg',N'Kg',105000,20,3),
        (5,N'Đùi gà góc tư',N'Đùi gà tươi dùng chiên và nướng.',N'CP',N'Images/Products/dui-ga.jpg',N'Kg',85000,18,3),
        (5,N'Cánh gà',N'Cánh gà tươi dùng chiên hoặc nướng.',N'CP',N'Images/Products/canh-ga.jpg',N'Kg',98000,16,3),
        (5,N'Trứng gà hộp 10 quả',N'Trứng gà tươi đóng khay 10 quả.',N'Ba Huân',N'Images/Products/trung-ga.jpg',N'Hộp',32000,40,21),
        (5,N'Trứng vịt hộp 10 quả',N'Trứng vịt tươi đóng khay 10 quả.',N'V.Food',N'Images/Products/trung-vit.jpg',N'Hộp',35000,25,21),
        (5,N'Cá basa phi lê',N'Phi lê cá basa đã sơ chế.',N'Agifish',N'Images/Products/ca-basa.jpg',N'Kg',85000,12,2),
        (5,N'Cá hồi phi lê',N'Phi lê cá hồi bảo quản lạnh.',N'Na Uy',N'Images/Products/ca-hoi.jpg',N'Kg',420000,5,2),
        (5,N'Cá thu cắt lát',N'Cá thu cắt lát tươi dùng kho hoặc chiên.',N'Hải sản Việt',N'Images/Products/ca-thu.jpg',N'Kg',190000,8,2),
        (5,N'Tôm thẻ tươi',N'Tôm thẻ tươi đã phân loại.',N'Hải sản Việt',N'Images/Products/tom-the.jpg',N'Kg',180000,10,2),
        (5,N'Mực ống tươi',N'Mực ống tươi dùng hấp, xào hoặc nướng.',N'Hải sản Việt',N'Images/Products/muc-ong.jpg',N'Kg',230000,7,2),
        (5,N'Xúc xích tiệt trùng',N'Xúc xích ăn liền đóng gói.',N'Đức Việt',N'Images/Products/xuc-xich.jpg',N'Gói',38000,35,120),
        (5,N'Giò lụa 500g',N'Giò lụa đóng gói.',N'Vissan',N'Images/Products/gio-lua.jpg',N'Khoanh',95000,12,20),
        (5,N'Thịt viên đông lạnh',N'Thịt viên đông lạnh tiện lợi chế biến.',N'CP',N'Images/Products/thit-vien.jpg',N'Gói',68000,15,180),
        (5,N'Cá viên đông lạnh',N'Cá viên đông lạnh dùng nấu lẩu và chiên.',N'Đôi Đũa Vàng',N'Images/Products/ca-vien.jpg',N'Gói',52000,20,180),

        -- =====================================
        -- 6. BÁNH KẸO (20 SP)
        -- =====================================

        (6,N'Bánh quy bơ Danisa',N'Bánh quy bơ giòn thơm đóng hộp.',N'Danisa',N'Images/Products/danisa.jpg',N'Hộp',115000,20,240),
        (6,N'Bánh quy sữa Cosy',N'Bánh quy vị sữa dùng ăn nhẹ.',N'Cosy',N'Images/Products/cosy.jpg',N'Gói',32000,35,180),
        (6,N'Bánh cracker AFC',N'Bánh cracker vị mặn giòn xốp.',N'AFC',N'Images/Products/afc.jpg',N'Gói',28000,40,180),
        (6,N'Bánh gạo One One',N'Bánh gạo giòn vị truyền thống.',N'One One',N'Images/Products/one-one.jpg',N'Gói',26000,30,180),
        (6,N'Bánh xốp KitKat',N'Bánh xốp nhân kem chocolate.',N'KitKat',N'Images/Products/kitkat.jpg',N'Thanh',15000,60,240),
        (6,N'Bánh bông lan Solite',N'Bánh bông lan cuộn nhân kem.',N'Solite',N'Images/Products/solite.jpg',N'Hộp',42000,25,60),
        (6,N'Bánh mì sandwich',N'Bánh mì sandwich mềm dùng ăn sáng.',N'Kinh Đô',N'Images/Products/sandwich.jpg',N'Gói',28000,20,5),
        (6,N'Bánh mì ngọt nhân sữa',N'Bánh mì ngọt nhân kem sữa.',N'Staff',N'Images/Products/banh-mi-ngot.jpg',N'Cái',12000,35,5),
        (6,N'Kẹo bạc hà Mentos',N'Kẹo bạc hà the mát.',N'Mentos',N'Images/Products/mentos.jpg',N'Cuộn',18000,45,540),
        (6,N'Kẹo dẻo Haribo',N'Kẹo dẻo nhiều hương vị trái cây.',N'Haribo',N'Images/Products/haribo.jpg',N'Gói',35000,25,365),
        (6,N'Kẹo chocolate M&M',N'Kẹo chocolate sữa viên nhỏ.',N'M&M',N'Images/Products/mm.jpg',N'Gói',30000,30,365),
        (6,N'Kẹo cao su Doublemint',N'Kẹo cao su hương bạc hà.',N'Doublemint',N'Images/Products/doublemint.jpg',N'Gói',12000,50,540),
        (6,N'Snack khoai tây Lay''s',N'Khoai tây lát chiên giòn vị tự nhiên.',N'Lay''s',N'Images/Products/lays.jpg',N'Gói',22000,45,180),
        (6,N'Snack bắp Oishi',N'Snack bắp giòn vị phô mai.',N'Oishi',N'Images/Products/oishi.jpg',N'Gói',10000,60,180),
        (6,N'Bắp rang bơ',N'Bắp rang bơ đóng gói ăn liền.',N'O''Corn',N'Images/Products/bap-rang-bo.jpg',N'Gói',25000,25,180),
        (6,N'Socola đen Lindt 70%',N'Chocolate đen hàm lượng cacao 70%.',N'Lindt',N'Images/Products/lindt.jpg',N'Thanh',89000,12,365),
        (6,N'Bánh quy yến mạch',N'Bánh quy yến mạch dùng ăn nhẹ.',N'Quaker',N'Images/Products/banh-yen-mach.jpg',N'Hộp',55000,18,180),
        (6,N'Bánh trung thu đậu xanh',N'Bánh trung thu nhân đậu xanh.',N'Kinh Đô',N'Images/Products/banh-trung-thu.jpg',N'Cái',65000,10,60),
        (6,N'Thạch trái cây',N'Thạch rau câu hương trái cây.',N'Long Hải',N'Images/Products/thach-trai-cay.jpg',N'Lốc',18000,40,180),
        (6,N'Kẹo dừa Bến Tre',N'Kẹo dừa mềm thơm vị dừa.',N'Bến Tre',N'Images/Products/keo-dua.jpg',N'Gói',28000,25,180),

        -- =====================================
        -- 7. GIA VỊ (20 SP)
        -- =====================================

        (7,N'Nước mắm Chinsu 500ml',N'Nước mắm cá cơm dùng nêm nếm và chấm.',N'Chinsu',N'Images/Products/nuoc-mam-chinsu.jpg',N'Chai',42000,35,730),
        (7,N'Nước mắm Nam Ngư 500ml',N'Nước mắm nhĩ đậm vị truyền thống.',N'Nam Ngư',N'Images/Products/nam-ngu.jpg',N'Chai',38000,40,730),
        (7,N'Nước tương Maggi 500ml',N'Nước tương đậu nành dùng chấm và chế biến.',N'Maggi',N'Images/Products/maggi.jpg',N'Chai',28000,45,540),
        (7,N'Dầu ăn Simply 1L',N'Dầu ăn thực vật dùng chiên xào.',N'Simply',N'Images/Products/simply.jpg',N'Chai',58000,30,540),
        (7,N'Dầu đậu nành Tường An 1L',N'Dầu đậu nành tinh luyện.',N'Tường An',N'Images/Products/tuong-an.jpg',N'Chai',52000,32,540),
        (7,N'Đường tinh luyện Biên Hòa',N'Đường tinh luyện dùng pha chế và nấu ăn.',N'Biên Hòa',N'Images/Products/duong.jpg',N'Gói',28000,50,730),
        (7,N'Đường phèn 500g',N'Đường phèn dùng nấu chè và pha thức uống.',N'Biên Hòa',N'Images/Products/duong-phen.jpg',N'Gói',25000,30,730),
        (7,N'Muối i-ốt 500g',N'Muối i-ốt dùng nêm nếm hằng ngày.',N'Bạc Liêu',N'Images/Products/muoi.jpg',N'Gói',8000,60,1095),
        (7,N'Hạt nêm Knorr 400g',N'Hạt nêm vị thịt heo dùng nấu ăn.',N'Knorr',N'Images/Products/knorr.jpg',N'Gói',32000,40,540),
        (7,N'Bột ngọt Ajinomoto 400g',N'Bột ngọt dùng điều vị món ăn.',N'Ajinomoto',N'Images/Products/ajinomoto.jpg',N'Gói',28000,35,730),
        (7,N'Tiêu đen xay 100g',N'Tiêu đen xay thơm cay dùng nêm nếm.',N'Dh Foods',N'Images/Products/tieu-den.jpg',N'Hũ',32000,20,540),
        (7,N'Ớt bột 100g',N'Ớt bột khô tạo vị cay.',N'Vianco',N'Images/Products/ot-bot.jpg',N'Gói',18000,25,365),
        (7,N'Tương ớt Chinsu',N'Tương ớt dùng chấm và ăn kèm.',N'Chinsu',N'Images/Products/tuong-ot.jpg',N'Chai',18000,40,365),
        (7,N'Tương cà',N'Tương cà chua dùng chấm và chế biến.',N'Ketchup',N'Images/Products/tuong-ca.jpg',N'Chai',20000,30,365),
        (7,N'Giấm gạo 500ml',N'Giấm gạo dùng trộn gỏi và pha nước chấm.',N'Ajinomoto',N'Images/Products/giam-gao.jpg',N'Chai',22000,25,540),
        (7,N'Bột cà ri Ấn Độ',N'Gia vị cà ri dạng bột.',N'Vianco',N'Images/Products/bot-ca-ri.jpg',N'Gói',15000,20,365),
        (7,N'Ngũ vị hương',N'Hỗn hợp gia vị dùng ướp thịt.',N'Ông Chà Và',N'Images/Products/ngu-vi-huong.jpg',N'Gói',7000,40,540),
        (7,N'Sốt mayonnaise Kewpie',N'Sốt mayonnaise dùng trộn salad.',N'Kewpie',N'Images/Products/mayonnaise.jpg',N'Chai',32000,22,180),
        (7,N'Dầu hào Maggi',N'Dầu hào dùng xào và ướp thực phẩm.',N'Maggi',N'Images/Products/dau-hao.jpg',N'Chai',35000,25,540),
        (7,N'Bột chiên giòn Tài Ký',N'Bột chiên giòn dùng chế biến món chiên.',N'Tài Ký',N'Images/Products/bot-chien-gion.jpg',N'Gói',16000,35,365),

        -- =====================================
        -- 8. THỰC PHẨM KHÔ (20 SP)
        -- =====================================

        (8,N'Gạo thơm Jasmine 5kg',N'Gạo thơm hạt dài dùng nấu cơm.',N'ST25',N'Images/Products/gao-jasmine.jpg',N'Túi',145000,25,365),
        (8,N'Gạo ST25 5kg',N'Gạo đặc sản thơm dẻo.',N'ST25',N'Images/Products/gao-st25.jpg',N'Túi',185000,20,365),
        (8,N'Gạo lứt đỏ 1kg',N'Gạo lứt đỏ dùng nấu cơm và cháo.',N'Việt San',N'Images/Products/gao-lut.jpg',N'Túi',42000,18,365),
        (8,N'Mì Hảo Hảo tôm chua cay',N'Mì ăn liền vị tôm chua cay.',N'Hảo Hảo',N'Images/Products/hao-hao.jpg',N'Gói',4500,200,180),
        (8,N'Mì Omachi bò hầm',N'Mì ăn liền hương vị bò hầm.',N'Omachi',N'Images/Products/omachi.jpg',N'Gói',7000,100,180),
        (8,N'Mì ly Modern',N'Mì ly tiện lợi vị thịt xào.',N'Modern',N'Images/Products/modern.jpg',N'Ly',12000,80,180),
        (8,N'Miến dong 500g',N'Miến dong khô dùng nấu canh và xào.',N'Viet San',N'Images/Products/mien-dong.jpg',N'Gói',45000,20,365),
        (8,N'Bún khô Safoco',N'Bún gạo khô dùng nấu bún và xào.',N'Safoco',N'Images/Products/bun-kho.jpg',N'Gói',28000,25,365),
        (8,N'Phở khô 500g',N'Bánh phở khô dùng chế biến món phở.',N'Vina Phở',N'Images/Products/pho-kho.jpg',N'Gói',32000,22,365),
        (8,N'Mì spaghetti Barilla',N'Mì Ý dạng sợi dùng nấu sốt.',N'Barilla',N'Images/Products/spaghetti.jpg',N'Gói',55000,20,730),
        (8,N'Yến mạch Quaker 500g',N'Yến mạch dùng nấu cháo và làm bánh.',N'Quaker',N'Images/Products/yen-mach.jpg',N'Hộp',68000,18,365),
        (8,N'Ngũ cốc Kellogg''s',N'Ngũ cốc ăn sáng dùng với sữa.',N'Kellogg''s',N'Images/Products/kelloggs.jpg',N'Hộp',85000,15,365),
        (8,N'Đậu xanh cà vỏ 500g',N'Đậu xanh cà vỏ dùng nấu chè.',N'Nông sản Việt',N'Images/Products/dau-xanh.jpg',N'Gói',32000,20,365),
        (8,N'Đậu đỏ 500g',N'Đậu đỏ khô dùng nấu chè và cháo.',N'Nông sản Việt',N'Images/Products/dau-do.jpg',N'Gói',35000,18,365),
        (8,N'Đậu đen xanh lòng',N'Đậu đen khô dùng nấu chè.',N'Nông sản Việt',N'Images/Products/dau-den.jpg',N'Gói',30000,20,365),
        (8,N'Nấm hương khô',N'Nấm hương sấy khô dùng nấu canh.',N'Nông sản Việt',N'Images/Products/nam-huong.jpg',N'Gói',55000,12,365),
        (8,N'Mộc nhĩ khô',N'Mộc nhĩ khô dùng chế biến món xào.',N'Nông sản Việt',N'Images/Products/moc-nhi.jpg',N'Gói',28000,15,365),
        (8,N'Rong biển nấu canh',N'Rong biển khô dùng nấu canh.',N'Hàn Quốc',N'Images/Products/rong-bien.jpg',N'Gói',35000,20,365),
        (8,N'Bột mì đa dụng 1kg',N'Bột mì dùng làm bánh và chế biến món ăn.',N'Meizan',N'Images/Products/bot-mi.jpg',N'Túi',26000,25,365),
        (8,N'Bột năng 400g',N'Bột năng dùng tạo độ sánh và làm bánh.',N'Tài Ký',N'Images/Products/bot-nang.jpg',N'Gói',14000,30,365),

        -- =====================================
        -- 9. HÓA MỸ PHẨM (20 SP)
        -- =====================================

        (9,N'Nước giặt OMO 2.7kg',N'Nước giặt dùng cho máy giặt cửa trước.',N'OMO',N'Images/Products/omo.jpg',N'Túi',165000,18,730),
        (9,N'Nước giặt Comfort 2.4kg',N'Nước giặt làm sạch và lưu hương.',N'Comfort',N'Images/Products/comfort.jpg',N'Túi',145000,20,730),
        (9,N'Bột giặt Ariel 3kg',N'Bột giặt dùng giặt tay và giặt máy.',N'Ariel',N'Images/Products/ariel.jpg',N'Túi',135000,22,730),
        (9,N'Nước xả vải Downy 1.8L',N'Nước xả vải giúp quần áo mềm và thơm.',N'Downy',N'Images/Products/downy.jpg',N'Chai',98000,20,730),
        (9,N'Nước rửa chén Sunlight',N'Nước rửa chén làm sạch dầu mỡ.',N'Sunlight',N'Images/Products/sunlight.jpg',N'Chai',32000,35,730),
        (9,N'Nước lau sàn Gift',N'Dung dịch lau sàn hương thơm.',N'Gift',N'Images/Products/gift.jpg',N'Chai',38000,25,730),
        (9,N'Nước tẩy toilet Vim',N'Dung dịch vệ sinh bồn cầu.',N'Vim',N'Images/Products/vim.jpg',N'Chai',35000,22,730),
        (9,N'Nước lau kính Gift',N'Dung dịch làm sạch kính.',N'Gift',N'Images/Products/nuoc-lau-kinh.jpg',N'Chai',28000,18,730),
        (9,N'Dầu gội Dove',N'Dầu gội làm sạch và chăm sóc tóc.',N'Dove',N'Images/Products/dove.jpg',N'Chai',145000,15,730),
        (9,N'Dầu xả Sunsilk',N'Dầu xả giúp tóc mềm mượt.',N'Sunsilk',N'Images/Products/sunsilk.jpg',N'Chai',68000,18,730),
        (9,N'Sữa tắm Lifebuoy',N'Sữa tắm làm sạch cơ thể.',N'Lifebuoy',N'Images/Products/lifebuoy.jpg',N'Chai',85000,20,730),
        (9,N'Xà phòng Lifebuoy',N'Xà phòng dùng vệ sinh cơ thể.',N'Lifebuoy',N'Images/Products/xa-phong.jpg',N'Bánh',18000,45,1095),
        (9,N'Kem đánh răng P/S',N'Kem đánh răng hương bạc hà.',N'P/S',N'Images/Products/ps.jpg',N'Tuýp',32000,40,1095),
        (9,N'Bàn chải Colgate',N'Bàn chải lông mềm vệ sinh răng miệng.',N'Colgate',N'Images/Products/colgate.jpg',N'Cái',25000,50,1095),
        (9,N'Nước súc miệng Listerine',N'Dung dịch súc miệng hương bạc hà.',N'Listerine',N'Images/Products/listerine.jpg',N'Chai',85000,18,730),
        (9,N'Khăn giấy Pulppy',N'Khăn giấy mềm dùng trong gia đình.',N'Pulppy',N'Images/Products/pulppy.jpg',N'Hộp',32000,35,1095),
        (9,N'Giấy vệ sinh Bless You',N'Giấy vệ sinh nhiều lớp mềm dai.',N'Bless You',N'Images/Products/bless-you.jpg',N'Lốc',65000,30,1095),
        (9,N'Nước rửa tay Lifebuoy',N'Dung dịch rửa tay hương dịu nhẹ.',N'Lifebuoy',N'Images/Products/rua-tay.jpg',N'Chai',55000,25,730),
        (9,N'Lăn khử mùi Rexona',N'Sản phẩm khử mùi cơ thể.',N'Rexona',N'Images/Products/rexona.jpg',N'Chai',68000,18,1095),
        (9,N'Kem chống nắng Sunplay',N'Kem chống nắng SPF50.',N'Sunplay',N'Images/Products/sunplay.jpg',N'Tuýp',125000,12,1095),

        -- =====================================
        -- 10. ĐỒ GIA DỤNG (20 SP)
        -- =====================================

        (10,N'Túi rác tự hủy cỡ nhỏ',N'Túi đựng rác tự hủy sinh học cỡ nhỏ.',N'Green Life',N'Images/Products/tui-rac-nho.jpg',N'Cuộn',18000,35,NULL),
        (10,N'Túi rác tự hủy cỡ lớn',N'Túi đựng rác tự hủy sinh học cỡ lớn.',N'Green Life',N'Images/Products/tui-rac-lon.jpg',N'Cuộn',28000,30,NULL),
        (10,N'Màng bọc thực phẩm',N'Màng bọc bảo quản thực phẩm trong tủ lạnh.',N'Ringo',N'Images/Products/mang-boc.jpg',N'Cuộn',35000,25,NULL),
        (10,N'Giấy bạc bọc thực phẩm',N'Giấy bạc dùng bọc và nướng thực phẩm.',N'Reynolds',N'Images/Products/giay-bac.jpg',N'Cuộn',42000,18,NULL),
        (10,N'Hộp đựng thực phẩm bộ 3',N'Bộ hộp nhựa đựng và bảo quản thực phẩm.',N'Duy Tân',N'Images/Products/hop-thuc-pham.jpg',N'Bộ',65000,20,NULL),
        (10,N'Ly nhựa dùng một lần',N'Ly nhựa dùng cho đồ uống và tiệc gia đình.',N'Hunufa',N'Images/Products/ly-nhua.jpg',N'Gói',25000,30,NULL),
        (10,N'Ống hút giấy',N'Ống hút giấy thân thiện môi trường.',N'Green',N'Images/Products/ong-hut.jpg',N'Gói',22000,25,NULL),
        (10,N'Khăn lau đa năng',N'Khăn lau dùng vệ sinh bếp và bề mặt.',N'3M',N'Images/Products/khan-lau.jpg',N'Cái',28000,30,NULL),
        (10,N'Miếng rửa chén',N'Miếng bọt biển dùng rửa chén bát.',N'Scotch-Brite',N'Images/Products/mieng-rua-chen.jpg',N'Gói',22000,35,NULL),
        (10,N'Găng tay cao su',N'Găng tay bảo vệ tay khi vệ sinh nhà cửa.',N'Hando',N'Images/Products/gang-tay.jpg',N'Đôi',35000,20,NULL),
        (10,N'Chổi quét nhà',N'Chổi nhựa dùng quét sàn nhà.',N'Duy Tân',N'Images/Products/choi-quet-nha.jpg',N'Cái',45000,12,NULL),
        (10,N'Cây lau nhà tự vắt',N'Bộ cây lau nhà có cơ chế vắt tiện lợi.',N'Kachi',N'Images/Products/cay-lau-nha.jpg',N'Bộ',185000,8,NULL),
        (10,N'Thau nhựa 30cm',N'Thau nhựa gia dụng đường kính 30cm.',N'Song Long',N'Images/Products/thau-nhua.jpg',N'Cái',35000,15,NULL),
        (10,N'Rổ nhựa đa năng',N'Rổ nhựa dùng đựng và rửa rau củ.',N'Duy Tân',N'Images/Products/ro-nhua.jpg',N'Cái',28000,20,NULL),
        (10,N'Móc áo nhựa 10 cái',N'Bộ móc áo nhựa dùng treo quần áo.',N'Duy Tân',N'Images/Products/moc-ao.jpg',N'Gói',30000,25,NULL),
        (10,N'Pin AA Panasonic',N'Pin tiểu AA dùng cho thiết bị gia đình.',N'Panasonic',N'Images/Products/pin-aa.jpg',N'Vỉ',42000,25,NULL),
        (10,N'Bóng đèn LED Rạng Đông 9W',N'Bóng đèn LED tiết kiệm điện.',N'Rạng Đông',N'Images/Products/bong-den-led.jpg',N'Cái',45000,15,NULL),
        (10,N'Bật lửa gas',N'Bật lửa gas sử dụng trong gia đình.',N'Thiên Long',N'Images/Products/bat-lua.jpg',N'Cái',12000,30,NULL),
        (10,N'Khẩu trang y tế 50 cái',N'Khẩu trang dùng một lần đóng hộp.',N'Bảo Thạch',N'Images/Products/khau-trang.jpg',N'Hộp',35000,40,NULL),
        (10,N'Tăm tre hộp 500 que',N'Tăm tre đóng hộp dùng trong gia đình.',N'Vina',N'Images/Products/tam-tre.jpg',N'Hộp',12000,35,NULL)

    ) AS p
    (
        MaNhom,
        TenSP,
        MoTa,
        ThuongHieu,
        Anh,
        DonViTinh,
        GiaBan,
        SoLuongTon,
        SoNgayHan
    )
    INNER JOIN dbo.DanhMuc dm
        ON dm.TenDM = CASE p.MaNhom
            WHEN 1 THEN N'Sữa và chế phẩm từ sữa'
            WHEN 2 THEN N'Đồ uống'
            WHEN 3 THEN N'Rau củ'
            WHEN 4 THEN N'Trái cây'
            WHEN 5 THEN N'Thịt và thủy sản'
            WHEN 6 THEN N'Bánh kẹo'
            WHEN 7 THEN N'Gia vị'
            WHEN 8 THEN N'Thực phẩm khô'
            WHEN 9 THEN N'Hóa mỹ phẩm'
            WHEN 10 THEN N'Đồ gia dụng'
        END
    WHERE NOT EXISTS
    (
        SELECT 1
        FROM dbo.SanPham sp
        WHERE sp.TenSP = p.TenSP
    );

    COMMIT TRANSACTION;

    PRINT N'Nạp dữ liệu danh mục và sản phẩm thành công!';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;


SELECT dm.TenDM, COUNT(*) AS SoSanPham
FROM dbo.SanPham sp
JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
GROUP BY dm.TenDM
ORDER BY dm.TenDM;

SELECT TOP 20
    sp.TenSP,
    dm.TenDM,
    sp.GiaBan,
    sp.DonViTinh,
    sp.SoLuongTon,
    sp.TrangThai
FROM dbo.SanPham sp
JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
ORDER BY sp.MaSP;

/*
===============================================================================
SMARTMART AI PRO - MIGRATION 001
Muc dich:
  - Mo rong database SmartMartAI hien co cho Hybrid Search, RAG, Embedding,
    Conversation Memory, feedback va theo doi bien dong gia/ton kho.
  - KHONG xoa, truncate, cap nhat hay nap lai du lieu trong 3 bang goc:
      dbo.DanhMuc, dbo.SanPham, dbo.SanPhamAnh.
  - Khong tu tao gia, ton kho, han su dung, lich su giao dich hoac embedding gia.
  - Co the chay lai an toan: cac bang/index da ton tai se duoc bo qua.

Yeu cau: SQL Server 2016+ (dung ISJSON), database SmartMartAI.
Khuyen nghi: backup database truoc khi chay; chay tren ban sao/staging truoc.
===============================================================================
*/

USE [SmartMartAI];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @MigrationVersion NVARCHAR(50) = N'001_SmartMart_AI_PRO';
DECLARE @MigrationDescription NVARCHAR(500) =
    N'Additive schema for hybrid search, RAG, embeddings, chat memory and audit';

BEGIN TRY
    BEGIN TRANSACTION;

    /* 0. Kiem tra schema nguon. Dung ngay neu file SQL goc chua duoc chay. */
    IF OBJECT_ID(N'dbo.DanhMuc', N'U') IS NULL
       OR OBJECT_ID(N'dbo.SanPham', N'U') IS NULL
       OR OBJECT_ID(N'dbo.SanPhamAnh', N'U') IS NULL
    BEGIN
        THROW 51000, N'Thieu bang goc DanhMuc/SanPham/SanPhamAnh. Hay tao database theo script goc truoc.', 1;
    END;

    IF COL_LENGTH(N'dbo.SanPham', N'MaSP') IS NULL
       OR COL_LENGTH(N'dbo.SanPham', N'TenSP') IS NULL
       OR COL_LENGTH(N'dbo.SanPham', N'GiaBan') IS NULL
       OR COL_LENGTH(N'dbo.SanPham', N'SoLuongTon') IS NULL
       OR COL_LENGTH(N'dbo.SanPham', N'TrangThai') IS NULL
    BEGIN
        THROW 51001, N'Cau truc dbo.SanPham khong dung voi schema SmartMartAI goc; migration da dung de tranh sua nham.', 1;
    END;

    /* 1. Bang ghi nhan migration. */
    IF OBJECT_ID(N'dbo.AI_MigrationHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_MigrationHistory
        (
            MigrationId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_MigrationHistory PRIMARY KEY,
            Version NVARCHAR(50) NOT NULL
                CONSTRAINT UQ_AI_MigrationHistory_Version UNIQUE,
            Description NVARCHAR(500) NULL,
            AppliedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_MigrationHistory_AppliedAt DEFAULT (SYSDATETIME()),
            AppliedBy NVARCHAR(128) NOT NULL
                CONSTRAINT DF_AI_MigrationHistory_AppliedBy DEFAULT (SUSER_SNAME())
        );
    END;

    IF EXISTS (SELECT 1 FROM dbo.AI_MigrationHistory WHERE Version = @MigrationVersion)
    BEGIN
        COMMIT TRANSACTION;
        PRINT N'Migration 001 da duoc ap dung truoc do. Khong co thay doi.';
        RETURN;
    END;

    /* 2. Tu dien tu dong / alias tieng Viet cho tim kiem san pham.
       Moi alias la mot dong; co the luu khong dau, viet tat, ten goi thuong dung. */
    IF OBJECT_ID(N'dbo.AI_ProductAlias', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_ProductAlias
        (
            AliasId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_ProductAlias PRIMARY KEY,
            MaSP INT NOT NULL,
            AliasText NVARCHAR(300) NOT NULL,
            NormalizedAlias NVARCHAR(300) NOT NULL,
            AliasType NVARCHAR(30) NOT NULL
                CONSTRAINT DF_AI_ProductAlias_AliasType DEFAULT (N'synonym'),
            LanguageCode NVARCHAR(10) NOT NULL
                CONSTRAINT DF_AI_ProductAlias_Language DEFAULT (N'vi'),
            IsActive BIT NOT NULL
                CONSTRAINT DF_AI_ProductAlias_IsActive DEFAULT (1),
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_ProductAlias_CreatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_ProductAlias_SanPham
                FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_AI_ProductAlias_Type
                CHECK (AliasType IN (N'synonym', N'no_accent', N'brand', N'misspelling', N'sku', N'other'))
        );
    END;

    /* 3. Log truy van tim kiem de danh gia chat luong Hybrid Search. */
    IF OBJECT_ID(N'dbo.AI_SearchLog', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_SearchLog
        (
            SearchLogId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_SearchLog PRIMARY KEY,
            ConversationId UNIQUEIDENTIFIER NULL,
            QueryText NVARCHAR(1000) NOT NULL,
            NormalizedQuery NVARCHAR(1000) NULL,
            SearchMode NVARCHAR(30) NOT NULL
                CONSTRAINT DF_AI_SearchLog_Mode DEFAULT (N'hybrid'),
            ResultCount INT NOT NULL
                CONSTRAINT DF_AI_SearchLog_ResultCount DEFAULT (0),
            SelectedMaSP INT NULL,
            LatencyMs INT NULL,
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_SearchLog_CreatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT CK_AI_SearchLog_Mode
                CHECK (SearchMode IN (N'keyword', N'fuzzy', N'semantic', N'hybrid'))
        );
    END;

    /* 4. Embedding san pham. Luu JSON de tuong thich nhieu phien ban SQL Server.
       Embedding phai duoc tao boi backend; migration KHONG tao vector gia. */
    IF OBJECT_ID(N'dbo.AI_ProductEmbedding', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_ProductEmbedding
        (
            ProductEmbeddingId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_ProductEmbedding PRIMARY KEY,
            MaSP INT NOT NULL,
            EmbeddingModel NVARCHAR(150) NOT NULL,
            EmbeddingVersion NVARCHAR(50) NULL,
            EmbeddingJson NVARCHAR(MAX) NOT NULL,
            ContentHash CHAR(64) NULL,
            SourceText NVARCHAR(2000) NULL,
            Dimensions INT NULL,
            IsActive BIT NOT NULL
                CONSTRAINT DF_AI_ProductEmbedding_IsActive DEFAULT (1),
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_ProductEmbedding_CreatedAt DEFAULT (SYSDATETIME()),
            UpdatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_ProductEmbedding_UpdatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_ProductEmbedding_SanPham
                FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_AI_ProductEmbedding_Json CHECK (ISJSON(EmbeddingJson) = 1),
            CONSTRAINT CK_AI_ProductEmbedding_Dimensions CHECK (Dimensions IS NULL OR Dimensions > 0)
        );
    END;

    /* 5. Nguon tri thuc RAG: chinh sach, huong dan, FAQ, quy dinh cua cua hang.
       Khong dung bang nay de luu gia/tồn kho hien hanh cua san pham. */
    IF OBJECT_ID(N'dbo.AI_KnowledgeDocument', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_KnowledgeDocument
        (
            DocumentId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_KnowledgeDocument PRIMARY KEY,
            Title NVARCHAR(300) NOT NULL,
            SourceType NVARCHAR(30) NOT NULL
                CONSTRAINT DF_AI_KnowledgeDocument_SourceType DEFAULT (N'faq'),
            SourceUri NVARCHAR(1000) NULL,
            VersionLabel NVARCHAR(100) NULL,
            LanguageCode NVARCHAR(10) NOT NULL
                CONSTRAINT DF_AI_KnowledgeDocument_Language DEFAULT (N'vi'),
            IsActive BIT NOT NULL
                CONSTRAINT DF_AI_KnowledgeDocument_IsActive DEFAULT (1),
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_KnowledgeDocument_CreatedAt DEFAULT (SYSDATETIME()),
            UpdatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_KnowledgeDocument_UpdatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT CK_AI_KnowledgeDocument_SourceType
                CHECK (SourceType IN (N'faq', N'policy', N'guide', N'web', N'file', N'other'))
        );
    END;

    IF OBJECT_ID(N'dbo.AI_KnowledgeChunk', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_KnowledgeChunk
        (
            ChunkId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_KnowledgeChunk PRIMARY KEY,
            DocumentId BIGINT NOT NULL,
            ChunkNo INT NOT NULL,
            ChunkText NVARCHAR(MAX) NOT NULL,
            TokenCount INT NULL,
            EmbeddingModel NVARCHAR(150) NULL,
            EmbeddingJson NVARCHAR(MAX) NULL,
            ContentHash CHAR(64) NULL,
            MetadataJson NVARCHAR(MAX) NULL,
            IsActive BIT NOT NULL
                CONSTRAINT DF_AI_KnowledgeChunk_IsActive DEFAULT (1),
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_KnowledgeChunk_CreatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_KnowledgeChunk_Document
                FOREIGN KEY (DocumentId) REFERENCES dbo.AI_KnowledgeDocument(DocumentId),
            CONSTRAINT UQ_AI_KnowledgeChunk_Document_Chunk UNIQUE (DocumentId, ChunkNo),
            CONSTRAINT CK_AI_KnowledgeChunk_EmbeddingJson
                CHECK (EmbeddingJson IS NULL OR ISJSON(EmbeddingJson) = 1),
            CONSTRAINT CK_AI_KnowledgeChunk_MetadataJson
                CHECK (MetadataJson IS NULL OR ISJSON(MetadataJson) = 1)
        );
    END;

    /* 6. Luu hoi thoai va tin nhan. Dung GUID de backend tao ID truoc khi insert.
       CustomerKey de NULL neu he thong chua co tai khoan khach hang. */
    IF OBJECT_ID(N'dbo.AI_Conversation', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_Conversation
        (
            ConversationId UNIQUEIDENTIFIER NOT NULL
                CONSTRAINT PK_AI_Conversation PRIMARY KEY,
            CustomerKey NVARCHAR(150) NULL,
            SessionKey NVARCHAR(150) NULL,
            Title NVARCHAR(300) NULL,
            Status NVARCHAR(20) NOT NULL
                CONSTRAINT DF_AI_Conversation_Status DEFAULT (N'active'),
            StartedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_Conversation_StartedAt DEFAULT (SYSDATETIME()),
            LastMessageAt DATETIME2(0) NULL,
            ClosedAt DATETIME2(0) NULL,
            MetadataJson NVARCHAR(MAX) NULL,
            CONSTRAINT CK_AI_Conversation_Status
                CHECK (Status IN (N'active', N'closed', N'archived')),
            CONSTRAINT CK_AI_Conversation_MetadataJson
                CHECK (MetadataJson IS NULL OR ISJSON(MetadataJson) = 1)
        );
    END;

    IF OBJECT_ID(N'dbo.AI_ChatMessage', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_ChatMessage
        (
            MessageId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_ChatMessage PRIMARY KEY,
            ConversationId UNIQUEIDENTIFIER NOT NULL,
            Role NVARCHAR(20) NOT NULL,
            Content NVARCHAR(MAX) NOT NULL,
            ToolName NVARCHAR(100) NULL,
            ToolArgumentsJson NVARCHAR(MAX) NULL,
            ToolResultJson NVARCHAR(MAX) NULL,
            ModelName NVARCHAR(150) NULL,
            InputTokens INT NULL,
            OutputTokens INT NULL,
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_ChatMessage_CreatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_ChatMessage_Conversation
                FOREIGN KEY (ConversationId) REFERENCES dbo.AI_Conversation(ConversationId),
            CONSTRAINT CK_AI_ChatMessage_Role
                CHECK (Role IN (N'system', N'user', N'assistant', N'tool')),
            CONSTRAINT CK_AI_ChatMessage_ToolArgumentsJson
                CHECK (ToolArgumentsJson IS NULL OR ISJSON(ToolArgumentsJson) = 1),
            CONSTRAINT CK_AI_ChatMessage_ToolResultJson
                CHECK (ToolResultJson IS NULL OR ISJSON(ToolResultJson) = 1)
        );
    END;

    IF OBJECT_ID(N'dbo.AI_ConversationSummary', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_ConversationSummary
        (
            SummaryId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_ConversationSummary PRIMARY KEY,
            ConversationId UNIQUEIDENTIFIER NOT NULL,
            SummaryText NVARCHAR(MAX) NOT NULL,
            SummaryVersion INT NOT NULL
                CONSTRAINT DF_AI_ConversationSummary_Version DEFAULT (1),
            ThroughMessageId BIGINT NULL,
            ImportantFactsJson NVARCHAR(MAX) NULL,
            UpdatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_ConversationSummary_UpdatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_ConversationSummary_Conversation
                FOREIGN KEY (ConversationId) REFERENCES dbo.AI_Conversation(ConversationId),
            CONSTRAINT CK_AI_ConversationSummary_FactsJson
                CHECK (ImportantFactsJson IS NULL OR ISJSON(ImportantFactsJson) = 1)
        );
    END;

    /* 7. Phan hoi nguoi dung de cai thien chat luong tu van. */
    IF OBJECT_ID(N'dbo.AI_Feedback', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_Feedback
        (
            FeedbackId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_Feedback PRIMARY KEY,
            ConversationId UNIQUEIDENTIFIER NULL,
            MessageId BIGINT NULL,
            Rating TINYINT NULL,
            FeedbackType NVARCHAR(30) NULL,
            Comment NVARCHAR(2000) NULL,
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_Feedback_CreatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_AI_Feedback_Conversation
                FOREIGN KEY (ConversationId) REFERENCES dbo.AI_Conversation(ConversationId),
            CONSTRAINT FK_AI_Feedback_Message
                FOREIGN KEY (MessageId) REFERENCES dbo.AI_ChatMessage(MessageId),
            CONSTRAINT CK_AI_Feedback_Rating CHECK (Rating IS NULL OR Rating BETWEEN 1 AND 5)
        );
    END;

    /* 8. Nhat ky bien dong kho. Khong tu dong ghi so lieu ton kho hien tai vao lich su.
       Backend/nghiep vu kho chi insert khi co phat sinh that. */
    IF OBJECT_ID(N'dbo.AI_StockMovement', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_StockMovement
        (
            StockMovementId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_StockMovement PRIMARY KEY,
            MaSP INT NOT NULL,
            MovementType NVARCHAR(20) NOT NULL,
            Quantity INT NOT NULL,
            ReferenceCode NVARCHAR(100) NULL,
            Note NVARCHAR(500) NULL,
            CreatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_StockMovement_CreatedAt DEFAULT (SYSDATETIME()),
            CreatedBy NVARCHAR(128) NULL,
            CONSTRAINT FK_AI_StockMovement_SanPham
                FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_AI_StockMovement_Type
                CHECK (MovementType IN (N'in', N'out', N'adjustment', N'return')),
            CONSTRAINT CK_AI_StockMovement_Quantity CHECK (Quantity > 0)
        );
    END;

    /* 9. Lich su gia chi duoc ghi tu thoi diem backend bat dau theo doi.
       Khong tao ban ghi lich su cho qua khu vi khong co du lieu nguon. */
    IF OBJECT_ID(N'dbo.AI_PriceHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_PriceHistory
        (
            PriceHistoryId BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_PriceHistory PRIMARY KEY,
            MaSP INT NOT NULL,
            OldPrice DECIMAL(18,2) NULL,
            NewPrice DECIMAL(18,2) NOT NULL,
            ChangedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_PriceHistory_ChangedAt DEFAULT (SYSDATETIME()),
            ChangedBy NVARCHAR(128) NULL,
            ChangeReason NVARCHAR(500) NULL,
            CONSTRAINT FK_AI_PriceHistory_SanPham
                FOREIGN KEY (MaSP) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_AI_PriceHistory_OldPrice CHECK (OldPrice IS NULL OR OldPrice >= 0),
            CONSTRAINT CK_AI_PriceHistory_NewPrice CHECK (NewPrice >= 0)
        );
    END;

    /* 10. Chi muc phuc vu truy van. */
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_ProductAlias_Normalized' AND object_id = OBJECT_ID(N'dbo.AI_ProductAlias'))
        CREATE INDEX IX_AI_ProductAlias_Normalized ON dbo.AI_ProductAlias(NormalizedAlias, IsActive) INCLUDE (MaSP, AliasType);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_ProductAlias_MaSP' AND object_id = OBJECT_ID(N'dbo.AI_ProductAlias'))
        CREATE INDEX IX_AI_ProductAlias_MaSP ON dbo.AI_ProductAlias(MaSP);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_ProductEmbedding_MaSP_Model' AND object_id = OBJECT_ID(N'dbo.AI_ProductEmbedding'))
        CREATE INDEX IX_AI_ProductEmbedding_MaSP_Model ON dbo.AI_ProductEmbedding(MaSP, EmbeddingModel, IsActive);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_KnowledgeChunk_Document' AND object_id = OBJECT_ID(N'dbo.AI_KnowledgeChunk'))
        CREATE INDEX IX_AI_KnowledgeChunk_Document ON dbo.AI_KnowledgeChunk(DocumentId, IsActive);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_Conversation_Customer_LastMessage' AND object_id = OBJECT_ID(N'dbo.AI_Conversation'))
        CREATE INDEX IX_AI_Conversation_Customer_LastMessage ON dbo.AI_Conversation(CustomerKey, LastMessageAt DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_ChatMessage_Conversation_Created' AND object_id = OBJECT_ID(N'dbo.AI_ChatMessage'))
        CREATE INDEX IX_AI_ChatMessage_Conversation_Created ON dbo.AI_ChatMessage(ConversationId, CreatedAt, MessageId);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_ConversationSummary_Conversation' AND object_id = OBJECT_ID(N'dbo.AI_ConversationSummary'))
        CREATE INDEX IX_AI_ConversationSummary_Conversation ON dbo.AI_ConversationSummary(ConversationId, UpdatedAt DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_SearchLog_Created' AND object_id = OBJECT_ID(N'dbo.AI_SearchLog'))
        CREATE INDEX IX_AI_SearchLog_Created ON dbo.AI_SearchLog(CreatedAt DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_StockMovement_MaSP_Created' AND object_id = OBJECT_ID(N'dbo.AI_StockMovement'))
        CREATE INDEX IX_AI_StockMovement_MaSP_Created ON dbo.AI_StockMovement(MaSP, CreatedAt DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AI_PriceHistory_MaSP_Changed' AND object_id = OBJECT_ID(N'dbo.AI_PriceHistory'))
        CREATE INDEX IX_AI_PriceHistory_MaSP_Changed ON dbo.AI_PriceHistory(MaSP, ChangedAt DESC);

    /* 11. Danh dau migration da hoan tat. */
    INSERT INTO dbo.AI_MigrationHistory (Version, Description)
    VALUES (@MigrationVersion, @MigrationDescription);

    COMMIT TRANSACTION;
    PRINT N'Migration SmartMart AI PRO 001 da hoan tat.';
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    DECLARE @Err NVARCHAR(2048) = ERROR_MESSAGE();
    THROW 51099, @Err, 1;
END CATCH;
GO

/* ============================================================================
KIEM TRA SAU MIGRATION (chi doc, khong sua du lieu)
============================================================================ */
USE [SmartMartAI];
GO

SELECT N'DanhMuc' AS Bang, COUNT_BIG(*) AS SoDong FROM dbo.DanhMuc
UNION ALL SELECT N'SanPham', COUNT_BIG(*) FROM dbo.SanPham
UNION ALL SELECT N'SanPhamAnh', COUNT_BIG(*) FROM dbo.SanPhamAnh;

SELECT Version, Description, AppliedAt, AppliedBy
FROM dbo.AI_MigrationHistory
ORDER BY MigrationId;

SELECT t.name AS BangMoi
FROM sys.tables AS t
WHERE t.name LIKE N'AI[_]%'
ORDER BY t.name;
GO

/*
GHI CHU TICH HOP BACKEND:
- SanPham.GiaBan va SanPham.SoLuongTon van la NGUON DU LIEU CHUAN cho gia/ton kho hien tai.
- AI_ProductAlias: backend them alias sau khi duyet; khong tu dong them alias sai.
- AI_ProductEmbedding: backend tao embedding theo model/version va luu JSON array.
- AI_KnowledgeDocument/Chunk: chi nap tai lieu FAQ/chinh sach da duoc xac minh.
- AI_Conversation/AI_ChatMessage/AI_ConversationSummary: dung cho memory hoi thoai.
- AI_StockMovement va AI_PriceHistory: chi ghi nhan bien dong that tu nghiep vu; migration
  khong backfill lich su gia/ton kho khong ton tai.
- EmbeddingJson la JSON de luu tru; semantic retrieval co the tinh bang FAISS trong Python
  hoac vector store rieng. Khong nen scan/tinh cosine tren toan bo NVARCHAR(MAX) bang SQL.
- Neu ung dung da co bang chat cu, KHONG tu dong xoa/doi ten. Hay map ORM sang bang cu
  hoac lap migration rieng sau khi kiem tra chinh xac schema cu.
*/
