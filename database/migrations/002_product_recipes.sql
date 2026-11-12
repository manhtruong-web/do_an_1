SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.AI_MigrationHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AI_MigrationHistory
        (
            MigrationId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AI_MigrationHistory PRIMARY KEY,
            Version NVARCHAR(100) NOT NULL
                CONSTRAINT UQ_AI_MigrationHistory_Version UNIQUE,
            Description NVARCHAR(1000) NULL,
            AppliedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_AI_MigrationHistory_AppliedAt DEFAULT (SYSDATETIME()),
            AppliedBy NVARCHAR(256) NOT NULL
                CONSTRAINT DF_AI_MigrationHistory_AppliedBy DEFAULT (SUSER_SNAME())
        );
    END;

    IF OBJECT_ID(N'dbo.RecipeCategory', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.RecipeCategory
        (
            RecipeCategoryID INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_RecipeCategory PRIMARY KEY,
            CategoryName NVARCHAR(120) NOT NULL
                CONSTRAINT UQ_RecipeCategory_CategoryName UNIQUE,
            Description NVARCHAR(500) NULL
        );
    END;

    IF OBJECT_ID(N'dbo.ProductCookingClassification', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProductCookingClassification
        (
            ProductID INT NOT NULL
                CONSTRAINT PK_ProductCookingClassification PRIMARY KEY,
            Classification VARCHAR(32) NOT NULL,
            IsCookable BIT NOT NULL,
            RecipeGenerationAllowed BIT NOT NULL,
            ClassificationReason NVARCHAR(2000) NOT NULL,
            Confidence DECIMAL(5,4) NOT NULL,
            GeneratedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_ProductCookingClassification_GeneratedAt DEFAULT (SYSDATETIME()),
            ReviewStatus VARCHAR(20) NOT NULL
                CONSTRAINT DF_ProductCookingClassification_ReviewStatus DEFAULT ('needs_review'),
            RecipeGenerationStatus VARCHAR(20) NOT NULL
                CONSTRAINT DF_ProductCookingClassification_RecipeStatus DEFAULT ('pending'),
            RecipeCount INT NOT NULL
                CONSTRAINT DF_ProductCookingClassification_RecipeCount DEFAULT (0),
            InputHash CHAR(64) NOT NULL,
            ModelName NVARCHAR(100) NOT NULL,
            LastError NVARCHAR(1000) NULL,
            RecipeGenerationNote NVARCHAR(1000) NULL,
            UpdatedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_ProductCookingClassification_UpdatedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_ProductCookingClassification_SanPham
                FOREIGN KEY (ProductID) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_ProductCookingClassification_Type CHECK
                (Classification IN
                    ('COOKING_INGREDIENT', 'FOOD_PROCESSABLE', 'READY_TO_EAT', 'BEVERAGE', 'NON_FOOD', 'UNKNOWN')),
            CONSTRAINT CK_ProductCookingClassification_Confidence CHECK
                (Confidence >= 0 AND Confidence <= 1),
            CONSTRAINT CK_ProductCookingClassification_ReviewStatus CHECK
                (ReviewStatus IN ('needs_review', 'approved', 'rejected', 'failed')),
            CONSTRAINT CK_ProductCookingClassification_RecipeStatus CHECK
                (RecipeGenerationStatus IN ('pending', 'not_applicable', 'complete', 'failed')),
            CONSTRAINT CK_ProductCookingClassification_RecipeCount CHECK (RecipeCount >= 0)
        );
    END;

    IF COL_LENGTH(N'dbo.ProductCookingClassification', N'RecipeGenerationNote') IS NULL
        ALTER TABLE dbo.ProductCookingClassification
            ADD RecipeGenerationNote NVARCHAR(1000) NULL;

    IF OBJECT_ID(N'dbo.Recipe', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Recipe
        (
            RecipeID BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_Recipe PRIMARY KEY,
            PrimaryProductID INT NOT NULL,
            RecipeCategoryID INT NULL,
            RecipeKey CHAR(64) NOT NULL,
            RecipeName NVARCHAR(300) NOT NULL,
            Description NVARCHAR(2000) NOT NULL,
            ImageURL NVARCHAR(1000) NULL,
            PreparationTimeMinutes INT NOT NULL,
            CookingTimeMinutes INT NOT NULL,
            Servings SMALLINT NOT NULL,
            Difficulty VARCHAR(20) NOT NULL,
            Instructions NVARCHAR(MAX) NOT NULL,
            Tips NVARCHAR(2000) NOT NULL,
            SafetyNotes NVARCHAR(2000) NOT NULL,
            Status VARCHAR(20) NOT NULL
                CONSTRAINT DF_Recipe_Status DEFAULT ('ai_generated'),
            SourceModel NVARCHAR(100) NOT NULL,
            GeneratedAt DATETIME2(0) NOT NULL
                CONSTRAINT DF_Recipe_GeneratedAt DEFAULT (SYSDATETIME()),
            CONSTRAINT FK_Recipe_PrimaryProduct
                FOREIGN KEY (PrimaryProductID) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT FK_Recipe_RecipeCategory
                FOREIGN KEY (RecipeCategoryID) REFERENCES dbo.RecipeCategory(RecipeCategoryID),
            CONSTRAINT CK_Recipe_PreparationTime CHECK (PreparationTimeMinutes >= 0),
            CONSTRAINT CK_Recipe_CookingTime CHECK (CookingTimeMinutes >= 0),
            CONSTRAINT CK_Recipe_Servings CHECK (Servings BETWEEN 1 AND 100),
            CONSTRAINT CK_Recipe_Difficulty CHECK (Difficulty IN ('easy', 'medium', 'hard')),
            CONSTRAINT CK_Recipe_Instructions_JSON CHECK (ISJSON(Instructions) = 1),
            CONSTRAINT CK_Recipe_Status CHECK (Status IN ('ai_generated', 'approved', 'archived'))
        );
    END;

    IF OBJECT_ID(N'dbo.RecipeIngredient', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.RecipeIngredient
        (
            RecipeIngredientID BIGINT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_RecipeIngredient PRIMARY KEY,
            RecipeID BIGINT NOT NULL,
            ProductID INT NULL,
            IngredientName NVARCHAR(300) NOT NULL,
            Quantity DECIMAL(12,3) NOT NULL,
            Unit NVARCHAR(50) NOT NULL,
            IsPrimary BIT NOT NULL
                CONSTRAINT DF_RecipeIngredient_IsPrimary DEFAULT (0),
            IsAvailableInStore BIT NOT NULL,
            Notes NVARCHAR(500) NULL,
            CONSTRAINT FK_RecipeIngredient_Recipe
                FOREIGN KEY (RecipeID) REFERENCES dbo.Recipe(RecipeID),
            CONSTRAINT FK_RecipeIngredient_Product
                FOREIGN KEY (ProductID) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT CK_RecipeIngredient_Quantity CHECK (Quantity > 0),
            CONSTRAINT CK_RecipeIngredient_ProductAvailability CHECK
                ((ProductID IS NOT NULL AND IsAvailableInStore = 1)
                 OR (ProductID IS NULL AND IsAvailableInStore = 0))
        );
    END;

    IF OBJECT_ID(N'dbo.ProductRecipe', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProductRecipe
        (
            ProductID INT NOT NULL,
            RecipeID BIGINT NOT NULL,
            RelationType VARCHAR(20) NOT NULL,
            CONSTRAINT PK_ProductRecipe PRIMARY KEY (ProductID, RecipeID),
            CONSTRAINT FK_ProductRecipe_Product
                FOREIGN KEY (ProductID) REFERENCES dbo.SanPham(MaSP),
            CONSTRAINT FK_ProductRecipe_Recipe
                FOREIGN KEY (RecipeID) REFERENCES dbo.Recipe(RecipeID),
            CONSTRAINT CK_ProductRecipe_RelationType CHECK
                (RelationType IN ('primary', 'ingredient'))
        );
    END;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.Recipe') AND name = N'UX_Recipe_PrimaryProduct_RecipeKey'
    )
        CREATE UNIQUE INDEX UX_Recipe_PrimaryProduct_RecipeKey
            ON dbo.Recipe(PrimaryProductID, RecipeKey);

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.Recipe') AND name = N'IX_Recipe_PrimaryProduct_Status'
    )
        CREATE INDEX IX_Recipe_PrimaryProduct_Status
            ON dbo.Recipe(PrimaryProductID, Status, RecipeID);

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.RecipeIngredient') AND name = N'IX_RecipeIngredient_ProductID'
    )
        CREATE INDEX IX_RecipeIngredient_ProductID
            ON dbo.RecipeIngredient(ProductID, RecipeID)
            INCLUDE (IngredientName, IsAvailableInStore);

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.ProductCookingClassification')
          AND name = N'IX_ProductCookingClassification_Type_Status'
    )
        CREATE INDEX IX_ProductCookingClassification_Type_Status
            ON dbo.ProductCookingClassification(Classification, RecipeGenerationStatus, ProductID)
            INCLUDE (IsCookable, RecipeGenerationAllowed, ReviewStatus, RecipeCount);

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.ProductRecipe') AND name = N'IX_ProductRecipe_RecipeID'
    )
        CREATE INDEX IX_ProductRecipe_RecipeID
            ON dbo.ProductRecipe(RecipeID, RelationType)
            INCLUDE (ProductID);

    IF NOT EXISTS
    (
        SELECT 1 FROM dbo.AI_MigrationHistory WHERE Version = N'002_Product_Recipes'
    )
        INSERT INTO dbo.AI_MigrationHistory (Version, Description)
        VALUES
        (
            N'002_Product_Recipes',
            N'Add product cooking classifications, AI recipe storage, ingredient links, and recipe categories'
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
