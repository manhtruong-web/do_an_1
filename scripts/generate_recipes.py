from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.recipe_service import (
    ClassificationItem,
    GeminiRecipeGenerator,
    RecipeProviderError,
    classify_with_retry,
    generate_recipes_with_retry,
    persist_classification,
    persist_recipe,
    product_input_hash,
    record_classification_failure,
    set_recipe_generation_status,
)

logger = logging.getLogger("smartmart.recipe_generation")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify SmartMart products and generate grounded recipe drafts."
    )
    parser.add_argument("--batch-size", type=int, default=5, choices=range(1, 21))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--product-ids", help="Comma-separated product IDs.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--classification-only", action="store_true")
    parser.add_argument("--recipes-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    return parser.parse_args()


def _load_products(db: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    conditions = ["sp.TrangThai = 1"]
    params: dict[str, Any] = {}
    product_ids = None
    if args.product_ids:
        try:
            product_ids = list(dict.fromkeys(int(item.strip()) for item in args.product_ids.split(",")))
        except ValueError as exc:
            raise SystemExit("--product-ids must contain comma-separated positive integers.") from exc
        if not product_ids or any(product_id <= 0 for product_id in product_ids):
            raise SystemExit("--product-ids must contain comma-separated positive integers.")
        conditions.append(
            "sp.MaSP IN (" + ", ".join(f":product_id_{index}" for index in range(len(product_ids))) + ")"
        )
        params.update({f"product_id_{index}": value for index, value in enumerate(product_ids)})

    top = ""
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be greater than zero.")
        top = f"TOP ({min(args.limit, 200)})"

    rows = db.execute(
        text(f"""
            SELECT {top} sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc, sp.MoTa,
                   sp.ThuongHieu, sp.DonViTinh
            FROM dbo.SanPham sp
            INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
            WHERE {' AND '.join(conditions)}
            ORDER BY sp.MaSP
        """),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _classification_for(db: Any, product_id: int) -> ClassificationItem | None:
    row = db.execute(
        text("""
            SELECT ProductID, Classification, IsCookable, RecipeGenerationAllowed,
                   ClassificationReason, Confidence
            FROM dbo.ProductCookingClassification
            WHERE ProductID = :product_id
        """),
        {"product_id": product_id},
    ).mappings().first()
    if row is None:
        return None
    return ClassificationItem(
        product_id=int(row["ProductID"]),
        classification=row["Classification"],
        is_cookable=bool(row["IsCookable"]),
        recipe_generation_allowed=bool(row["RecipeGenerationAllowed"]),
        classification_reason=row["ClassificationReason"],
        confidence=float(row["Confidence"]),
    )


def _existing_status(db: Any, product_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text("""
            SELECT InputHash, ReviewStatus, RecipeGenerationStatus, RecipeCount
            FROM dbo.ProductCookingClassification
            WHERE ProductID = :product_id
        """),
        {"product_id": product_id},
    ).mappings().first()
    return dict(row) if row else None


def _classify(
    db: Any,
    products: list[dict[str, Any]],
    generator: GeminiRecipeGenerator,
    batch_size: int,
    force: bool,
    pause_seconds: float,
) -> None:
    batches = [
        products[index:index + batch_size]
        for index in range(0, len(products), batch_size)
    ]
    for batch in batches:
        to_process = []
        for product in batch:
            existing = _existing_status(db, int(product["MaSP"]))
            if (
                existing
                and existing["InputHash"] == product_input_hash(product)
                and existing["ReviewStatus"] != "failed"
                and not force
            ):
                continue
            to_process.append(product)
        if not to_process:
            continue

        try:
            classifications = classify_with_retry(generator, to_process)
        except RecipeProviderError as batch_error:
            logger.warning(
                "Classification batch failed; retrying individually (%s)",
                type(batch_error).__name__,
            )
            classifications = []
            for product in to_process:
                try:
                    classifications.extend(classify_with_retry(generator, [product]))
                except RecipeProviderError as exc:
                    record_classification_failure(
                        db,
                        product,
                        settings.gemini_model,
                        type(exc).__name__,
                    )
                    db.commit()
                    logger.error("Classification failed for product_id=%s", product["MaSP"])
                time.sleep(max(pause_seconds, 0))
        try:
            for classification in classifications:
                product = next(
                    item for item in to_process if int(item["MaSP"]) == classification.product_id
                )
                persist_classification(
                    db,
                    product,
                    classification,
                    settings.gemini_model,
                    force=force,
                )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist a classification batch.")
        time.sleep(max(pause_seconds, 0))


def _generate(
    db: Any,
    products: list[dict[str, Any]],
    generator: GeminiRecipeGenerator,
    force: bool,
    pause_seconds: float,
) -> None:
    for product in products:
        product_id = int(product["MaSP"])
        classification = _classification_for(db, product_id)
        if classification is None:
            logger.warning("Skipping unclassified product_id=%s", product_id)
            continue
        if (
            classification.classification not in {
                "COOKING_INGREDIENT",
                "FOOD_PROCESSABLE",
                "BEVERAGE",
            }
            or not classification.recipe_generation_allowed
        ):
            set_recipe_generation_status(db, product_id, "not_applicable", 0)
            db.commit()
            continue

        existing = _existing_status(db, product_id)
        if existing and existing["RecipeGenerationStatus"] == "complete" and not force:
            continue
        try:
            response = generate_recipes_with_retry(generator, product, classification)
            inserted = 0
            for recipe in response.recipes:
                _, created = persist_recipe(db, product, recipe, settings.gemini_model)
                inserted += int(created)
            active_count = int(
                db.execute(
                    text("""
                        SELECT COUNT(*) FROM dbo.Recipe
                        WHERE PrimaryProductID = :product_id
                          AND Status IN ('ai_generated', 'approved')
                    """),
                    {"product_id": product_id},
                ).scalar_one()
            )
            status = "complete" if response.recipes else "not_applicable"
            set_recipe_generation_status(
                db,
                product_id,
                status,
                active_count,
                note=response.not_suitable_reason if not response.recipes else None,
            )
            db.commit()
            logger.info(
                "Recipes processed for product_id=%s inserted=%s",
                product_id,
                inserted,
            )
        except Exception as exc:
            db.rollback()
            existing_count = int(
                db.execute(
                    text("""
                        SELECT COUNT(*) FROM dbo.Recipe
                        WHERE PrimaryProductID = :product_id
                          AND Status IN ('ai_generated', 'approved')
                    """),
                    {"product_id": product_id},
                ).scalar_one()
            )
            set_recipe_generation_status(
                db,
                product_id,
                "failed",
                existing_count,
                type(exc).__name__,
            )
            db.commit()
            logger.error(
                "Recipe generation failed for product_id=%s (%s)",
                product_id,
                type(exc).__name__,
            )
        time.sleep(max(pause_seconds, 0))

def _report(db: Any) -> dict[str, Any]:
    totals = db.execute(text("""
        SELECT COUNT(*) AS TotalProducts,
               SUM(CASE WHEN pc.ProductID IS NOT NULL THEN 1 ELSE 0 END) AS ClassifiedProducts
        FROM dbo.SanPham sp
        LEFT JOIN dbo.ProductCookingClassification pc ON pc.ProductID = sp.MaSP
        WHERE sp.TrangThai = 1
    """)).mappings().one()
    classification_rows = db.execute(text("""
        SELECT Classification, COUNT(*) AS ProductCount
        FROM dbo.ProductCookingClassification pc
        INNER JOIN dbo.SanPham sp ON sp.MaSP = pc.ProductID
        WHERE sp.TrangThai = 1
        GROUP BY Classification ORDER BY Classification
    """)).mappings().all()
    category_rows = db.execute(text("""
        SELECT dm.TenDM AS CategoryName, pc.Classification, COUNT(*) AS ProductCount
        FROM dbo.ProductCookingClassification pc
        INNER JOIN dbo.SanPham sp ON sp.MaSP = pc.ProductID
        INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
        WHERE sp.TrangThai = 1
        GROUP BY dm.TenDM, pc.Classification
        ORDER BY dm.TenDM, pc.Classification
    """)).mappings().all()
    recipe_rows = db.execute(text("""
        SELECT COUNT(*) AS RecipeCount,
               SUM(CASE WHEN Status = 'ai_generated' THEN 1 ELSE 0 END) AS AIGenerated,
               SUM(CASE WHEN Status = 'approved' THEN 1 ELSE 0 END) AS Approved
        FROM dbo.Recipe
    """)).mappings().one()
    ingredient_rows = db.execute(text("""
        SELECT COUNT(*) AS TotalIngredients,
               SUM(CASE WHEN ProductID IS NOT NULL THEN 1 ELSE 0 END) AS MatchedIngredients,
               SUM(CASE WHEN ProductID IS NULL THEN 1 ELSE 0 END) AS ExternalIngredients
        FROM dbo.RecipeIngredient
    """)).mappings().one()
    failures = db.execute(text("""
        SELECT
            SUM(CASE WHEN ReviewStatus = 'failed' THEN 1 ELSE 0 END) AS ClassificationFailures,
            SUM(CASE WHEN RecipeGenerationStatus = 'failed' THEN 1 ELSE 0 END) AS RecipeFailures,
            SUM(CASE WHEN Classification = 'UNKNOWN' THEN 1 ELSE 0 END) AS UnknownProducts
        FROM dbo.ProductCookingClassification
    """)).mappings().one()
    return {
        "catalog": dict(totals),
        "classifications": [dict(row) for row in classification_rows],
        "category_classifications": [dict(row) for row in category_rows],
        "recipes": dict(recipe_rows),
        "ingredients": dict(ingredient_rows),
        "failures": dict(failures),
    }


def main() -> int:
    args = _arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.classification_only and args.recipes_only:
        raise SystemExit("--classification-only and --recipes-only cannot be combined.")
    if SessionLocal is None:
        raise SystemExit("DATABASE_URL is not configured.")
    with SessionLocal() as db:
        products = _load_products(db, args)
        if args.dry_run:
            print(json.dumps({"selected_products": len(products)}, ensure_ascii=False))
            return 0
        generator = GeminiRecipeGenerator()
        if not args.recipes_only:
            _classify(
                db,
                products,
                generator,
                batch_size=args.batch_size,
                force=args.force,
                pause_seconds=args.pause_seconds,
            )
        if not args.classification_only:
            _generate(
                db,
                products,
                generator,
                force=args.force,
                pause_seconds=args.pause_seconds,
            )
        report = _report(db)
    print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
