"""API FastAPI cho tìm kiếm sản phẩm, chatbot AI và tìm kiếm ảnh từ SQL Server."""

import base64
import binascii
import hmac
import json
import logging
import time
from io import BytesIO
from typing import Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .assistant import answer_question
from .config import settings
from .database import get_db
from .gemini_service import GeminiProviderError, answer_with_gemini
from .image_service import (
    FaissProductIndex,
    sync_product_image_embeddings,
)
from .product_images import (
    ALLOWED_IMAGE_TYPES,
    DEFAULT_PRODUCT_IMAGE,
    resolve_product_image_path,
)
from .products import (
    get_product_by_id,
    get_product_filter_options,
    list_categories,
    search_products,
)
from .recipe_service import get_classification, get_product_recipes
from .visual_search import (
    VisualSearchEngine,
    get_search_result_page,
    record_visual_search_event,
    record_visual_search_feedback,
    visual_search_metrics,
)
from .visual_search_admin import (
    get_visual_index_job,
    run_visual_index_job,
    schedule_visual_index_job,
)

logger = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(title=settings.app_name, default_response_class=UTF8JSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(default="", max_length=1000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=24)
    recent_product_ids: list[int] = Field(default_factory=list, max_length=30)
    image_base64: str | None = None
    conversation_id: str | None = None


class VisualSearchFeedback(BaseModel):
    search_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    product_id: int = Field(gt=0)
    action: Literal["selected", "helpful", "not_helpful"]


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = settings.admin_api_token.strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Dashboard quản trị chưa được cấu hình ADMIN_API_TOKEN.",
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Không có quyền quản trị.")


# ---------------------------------------------------------------------------
# Health & Static
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _image_headers(status: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Image-Status": status,
    }


def _product_image_url(product: dict) -> dict:
    product_with_image_url = dict(product)
    product_id = product_with_image_url.get("MaSP")
    product_with_image_url["Anh"] = (
        f"/api/products/{product_id}/image"
        if isinstance(product_id, int) and product_id > 0
        else None
    )
    return product_with_image_url


def _products_with_image_urls(items: list[dict]) -> list[dict]:
    return [_product_image_url(item) for item in items]


def _with_product_image_urls(payload: dict) -> dict:
    result = dict(payload)
    if isinstance(result.get("products"), list):
        result["products"] = _products_with_image_urls(result["products"])
    return result


@app.get("/api/products/default-image")
def default_product_image() -> Response:
    """Return a local, non-product-specific placeholder for missing images."""
    return Response(
        content=DEFAULT_PRODUCT_IMAGE,
        media_type="image/svg+xml",
        headers=_image_headers("placeholder"),
    )


@app.get("/api/products/{product_id}/image")
def product_image(product_id: int, db: Session = Depends(get_db)) -> Response:
    """Serve the product's local image file without exposing its disk path."""
    product = get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")

    image_path = resolve_product_image_path(product.get("Anh"))
    if image_path is None:
        status = "missing" if not product.get("Anh") else "unavailable"
        return Response(
            content=DEFAULT_PRODUCT_IMAGE,
            media_type="image/svg+xml",
            headers={**_image_headers(status), "X-Image-Source": "placeholder"},
        )

    return FileResponse(
        image_path,
        media_type=ALLOWED_IMAGE_TYPES[image_path.suffix.lower()],
        headers={**_image_headers("ok"), "X-Image-Source": "product"},
    )


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.get("/api/filters")
def product_filter_options(db: Session = Depends(get_db)):
    return get_product_filter_options(db)


@app.get("/api/products")
def products(
    keyword: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    brands: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    in_stock_only: bool = False,
    out_of_stock_only: bool = False,
    sort_by: Literal["relevance", "name", "price", "stock"] = "relevance",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    db: Session = Depends(get_db),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="Giá thấp nhất không thể lớn hơn giá cao nhất.")
    if in_stock_only and out_of_stock_only:
        raise HTTPException(status_code=422, detail="Chỉ có thể chọn một tình trạng tồn kho.")
    brand_filters = ([brand] if brand else []) + (brands or [])
    found_products = search_products(
        db,
        keyword,
        category,
        brand_filters or None,
        min_price,
        max_price,
        in_stock_only=in_stock_only,
        out_of_stock_only=out_of_stock_only,
        limit=limit,
        sort_by=sort_by,
        descending=order == "desc",
        offset=offset,
    )
    return _products_with_image_urls(found_products)


@app.get("/api/products/search")
def product_search(
    keyword: str | None = None,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    brands: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    in_stock_only: bool = False,
    out_of_stock_only: bool = False,
    sort_by: Literal["relevance", "name", "price", "stock"] = "relevance",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    db: Session = Depends(get_db),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="Giá thấp nhất không thể lớn hơn giá cao nhất.")
    if in_stock_only and out_of_stock_only:
        raise HTTPException(status_code=422, detail="Chỉ có thể chọn một tình trạng tồn kho.")
    brand_filters = ([brand] if brand else []) + (brands or [])
    found_products = search_products(
        db,
        keyword=keyword or q,
        category=category,
        brand=brand_filters or None,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        out_of_stock_only=out_of_stock_only,
        limit=limit,
        sort_by=sort_by,
        descending=order == "desc",
        offset=offset,
    )
    return _products_with_image_urls(found_products)


@app.get("/api/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    product = get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    return _product_image_url(product)


@app.get("/api/products/{product_id}/recipes")
def product_recipes(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    classification = get_classification(db, product_id)
    return {
        "product": _product_image_url(product),
        "classification": classification,
        "recipes": get_product_recipes(db, product_id),
    }


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    return list_categories(db)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    try:
        if payload.image_base64:
            encoded_image = payload.image_base64.split(",", 1)[-1]
            max_encoded_bytes = ((settings.max_image_size_mb * 1024 * 1024 + 2) // 3) * 4
            if len(encoded_image) > max_encoded_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Ảnh vượt quá giới hạn {settings.max_image_size_mb}MB.",
                )
            try:
                image_bytes = base64.b64decode(encoded_image, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(status_code=400, detail="Dữ liệu ảnh không hợp lệ.") from exc
            return _image_search_response(
                _process_image_content(image_bytes, db, payload.question),
                db,
                payload.question,
                payload.history,
            )

        result = answer_question(
            db,
            question=payload.question,
            history=payload.history,
            recent_product_ids=payload.recent_product_ids,
        )
        return _with_product_image_urls(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Chat request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Không thể xử lý câu hỏi lúc này. Vui lòng thử lại.",
        ) from exc


# ---------------------------------------------------------------------------
# Image Search (standalone panel - giữ tương thích cũ)
# ---------------------------------------------------------------------------

# @app.post("/api/image-search")
# async def image_search(
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
# ):
#     """Endpoint disabled as there is no FAISS index or product data source."""
#     return await _process_image_search(file, message=None, db=db, use_gemini=False)


@app.post("/api/chat/search-by-image")
async def chat_search_by_image(
    file: UploadFile = File(...),
    message: str | None = Form(default=None, max_length=1000),
    history: str | None = Form(default=None, max_length=32000),
    db: Session = Depends(get_db),
) -> dict:
    """Tìm sản phẩm từ ảnh và gợi ý văn bản tùy chọn."""
    content = await _read_limited_upload(file)
    return _image_search_response(
        _process_image_content(content, db, message),
        db,
        message or "",
        _parse_image_history(history),
    )


def _parse_image_history(history: str | None) -> list[dict[str, str]]:
    if not history:
        return []
    try:
        entries = json.loads(history)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Lịch sử hội thoại không hợp lệ.") from exc
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="Lịch sử hội thoại không hợp lệ.")
    messages = []
    for entry in entries[-12:]:
        role = entry.get("role") if isinstance(entry, dict) else None
        if (
            isinstance(role, str)
            and role in {"user", "assistant"}
            and isinstance(entry.get("content"), str)
        ):
            content = entry["content"].strip()
            if content:
                messages.append({"role": role, "content": content[:2000]})
    return messages


def _history_before_image_turn(
    history: list[dict[str, str]], question: str
) -> list[dict[str, str]]:
    if not history or history[-1]["role"] != "user":
        return history
    current_turn = question.strip() or "Tìm sản phẩm bằng ảnh."
    return history[:-1] if history[-1]["content"] == current_turn else history


def _image_search_fallback(products: list[dict]) -> str:
    lines = ["Mình đã đối chiếu ảnh với dữ liệu sản phẩm trong cửa hàng và tìm thấy:"]
    for product in products[:5]:
        price = product.get("GiaBan")
        price_label = f"{price} đồng" if price is not None else "giá chưa có dữ liệu"
        stock = product.get("SoLuongTon")
        unit = product.get("DonViTinh") or "sản phẩm"
        reasons = product.get("match_reason")
        reason = " · ".join(reasons[:2]) if isinstance(reasons, list) else ""
        stock_label = (
            f"còn {stock} {unit}" if stock is not None and stock > 0 else
            "hết hàng" if stock == 0 else
            "tồn kho chưa có dữ liệu"
        )
        lines.append(
            f"- {product.get('TenSP', 'Sản phẩm')} ({product.get('DanhMuc', 'chưa rõ danh mục')}): "
            f"{price_label}, {stock_label}."
            + (f" Lý do được đề xuất: {reason}." if reason else "")
        )
    lines.append(
        "Thông tin thành phần và hướng dẫn bảo quản chưa có trong dữ liệu sản phẩm."
    )
    return "\n".join(lines)


def _image_search_response(
    result: dict,
    db: Session,
    question: str = "",
    history: list[dict[str, str]] | None = None,
) -> dict:
    response = _with_product_image_urls(result)
    products = response.get("products") or []
    if products:
        answer = _image_search_fallback(products)
        consultation_source = "sql_fallback"
        suggestions = [
            "Có thể chế biến món gì từ sản phẩm này?",
            "Có sản phẩm nào rẻ hơn không?",
            "Sản phẩm vừa tìm thấy còn hàng không?",
            "So sánh các sản phẩm vừa tìm thấy.",
        ]
        consultation_question = (
            "Khách vừa tải ảnh để tìm sản phẩm tương tự. Hãy chủ động tư vấn các kết quả "
            "đã được đính kèm trong DỮ LIỆU SQL ĐÃ XÁC THỰC; giải thích ngắn gọn lý do "
            "phù hợp, nêu giá và tồn kho hiện tại nếu có. Nếu khách chưa nêu nhu cầu, "
            "đưa ra gợi ý sử dụng hoặc chế biến phổ thông phù hợp danh mục, và nói rõ "
            "thành phần/hướng dẫn sử dụng nào chưa có dữ liệu.\n"
            f"Câu hỏi của khách: {question.strip() or 'Chưa nêu câu hỏi cụ thể.'}"
        )
        try:
            consultation = answer_with_gemini(
                db,
                consultation_question,
                _history_before_image_turn(history or [], question),
                verified_products=products[:10],
                intent="image_product_consultation",
            )
        except GeminiProviderError as exc:
            logger.warning("Gemini image consultation failed: %s", str(exc))
            consultation = None
            answer += "\n\n(Gemini hiện không khả dụng; thông tin sản phẩm vẫn lấy từ SQL Server.)"
        if consultation and consultation.get("answer"):
            answer = consultation["answer"]
            consultation_source = "gemini"
            suggestions = consultation.get("suggestions") or suggestions
        elif not settings.gemini_configured:
            answer += "\n\n(Gemini chưa được cấu hình; câu trả lời hiện chỉ gồm dữ liệu SQL.)"
    else:
        answer = "Hiện tại tôi chưa tìm thấy sản phẩm có hình ảnh đủ tương đồng trong siêu thị. Bạn có thể thử ảnh rõ hơn hoặc nhập tên sản phẩm để tôi tìm kiếm."
        consultation_source = "image_search"
        suggestions = []
    response["products"] = products
    response["answer"] = answer
    response["suggestions"] = suggestions
    response["consultation_source"] = consultation_source
    return {
        **response,
        "intent": "image_search",
        "domain": "shopping",
        "source": "image_embedding",
        "search_mode": "openclip_hybrid",
    }


async def _read_limited_upload(file: UploadFile) -> bytes:
    max_bytes = settings.max_image_size_mb * 1024 * 1024
    content = bytearray()
    while chunk := await file.read(min(64 * 1024, max_bytes + 1 - len(content))):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Ảnh vượt quá giới hạn {settings.max_image_size_mb}MB.",
            )
    return bytes(content)


def _image_sharpness(image: Image.Image) -> float:
    gray = np.asarray(
        image.convert("L").resize((224, 224), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    laplacian = (
        4 * gray[1:-1, 1:-1]
        - gray[:-2, 1:-1]
        - gray[2:, 1:-1]
        - gray[1:-1, :-2]
        - gray[1:-1, 2:]
    )
    return float(np.var(laplacian))


def _process_image_content(
    content: bytes,
    db: Session,
    user_query: str | None = None,
) -> dict:
    """Kiểm tra ảnh tải lên rồi tìm sản phẩm tương tự trong SQL Server."""

    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Ảnh vượt quá giới hạn {settings.max_image_size_mb}MB.",
        )
    if len(content) < 8:
        raise HTTPException(status_code=400, detail="File tải lên quá nhỏ, không phải ảnh hợp lệ.")

    try:
        with Image.open(BytesIO(content)) as image_probe:
            fmt = (image_probe.format or "").upper()
            width, height = image_probe.size
            if width < 32 or height < 32:
                raise HTTPException(
                    status_code=400,
                    detail="Ảnh quá nhỏ để nhận diện; hãy tải ảnh có kích thước tối thiểu 32×32 pixel.",
                )
            if width * height > 20_000_000:
                raise HTTPException(
                    status_code=413,
                    detail="Kích thước ảnh vượt quá giới hạn 20 megapixel.",
                )
            image_probe.verify()
        if fmt not in {"JPEG", "PNG", "WEBP"}:
            raise HTTPException(
                status_code=415,
                detail=f"Định dạng '{fmt or 'không xác định'}' không được hỗ trợ. Chỉ dùng JPG, PNG hoặc WebP.",
            )
        with Image.open(BytesIO(content)) as decoded:
            decoded.load()
            image = ImageOps.exif_transpose(decoded)
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            image = image.copy()
        if _image_sharpness(image) < 20:
            raise HTTPException(
                status_code=400,
                detail="Ảnh quá mờ để so sánh đáng tin cậy; hãy chụp lại rõ nét hơn.",
            )
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=400,
            detail="File ảnh bị lỗi hoặc không thể giải mã.",
        ) from exc

    try:
        started = time.perf_counter()
        result = VisualSearchEngine.search(
            db,
            image,
            user_query=user_query,
            limit=settings.image_search_top_k,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        if result.get("search_id"):
            record_visual_search_event(
                search_id=result["search_id"],
                duration_ms=duration_ms,
                result_count=int(result.get("total_results") or 0),
                analysis_status=str(result.get("analysis_status") or "unknown"),
            )
        result["duration_ms"] = round(duration_ms, 2)
        return result
    except Exception as exc:
        logger.exception("Image similarity search failed")
        raise HTTPException(
            status_code=500,
            detail="Không thể so sánh hình ảnh lúc này. Vui lòng thử lại.",
        ) from exc


# ---------------------------------------------------------------------------
# Admin: Sync embeddings & rebuild FAISS index
# ---------------------------------------------------------------------------

@app.get("/api/chat/search-by-image/{search_id}")
def more_image_search_results(
    search_id: str,
    offset: int = Query(default=10, ge=0, le=1000),
    limit: int = Query(default=10, ge=1, le=10),
    db: Session = Depends(get_db),
) -> dict:
    page = get_search_result_page(db, search_id, offset, limit)
    if page is None:
        raise HTTPException(status_code=404, detail="Kết quả tìm kiếm đã hết hạn.")
    return _with_product_image_urls(page)


@app.post("/api/visual-search/feedback")
def visual_search_feedback(payload: VisualSearchFeedback) -> dict[str, bool]:
    helpful = True if payload.action == "helpful" else (
        False if payload.action == "not_helpful" else None
    )
    recorded = record_visual_search_feedback(
        payload.search_id,
        payload.product_id,
        helpful,
        payload.action,
    )
    if not recorded:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả tìm kiếm.")
    return {"recorded": True}


@app.get("/api/admin/visual-search/status")
def admin_visual_search_status(
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    inventory = db.execute(text("""
        SELECT COUNT(*) AS total_products,
               SUM(CASE
                   WHEN NULLIF(LTRIM(RTRIM(sp.Anh)), '') IS NOT NULL
                     OR EXISTS (
                         SELECT 1 FROM dbo.SanPhamAnh spa
                         WHERE spa.MaSP = sp.MaSP
                           AND NULLIF(LTRIM(RTRIM(spa.DuongDanAnhDataset)), '') IS NOT NULL
                     )
                   THEN 1 ELSE 0
               END) AS products_with_images
        FROM dbo.SanPham sp
        WHERE sp.TrangThai = 1
    """)).mappings().one()
    return {
        "inventory": {
            "total_products": int(inventory["total_products"] or 0),
            "products_with_images": int(inventory["products_with_images"] or 0),
        },
        "index": VisualSearchEngine.status(),
        "metrics": visual_search_metrics(),
        "job": get_visual_index_job(),
        "gemini_vision_enabled": settings.visual_search_vision_enabled,
    }


@app.get("/api/admin/visual-search/errors")
def admin_visual_search_errors(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return {
        "errors": VisualSearchEngine.status()["errors"],
        "job": get_visual_index_job(),
    }


@app.post("/api/admin/visual-search/sync", status_code=202)
def admin_start_visual_search_sync(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        job = schedule_visual_index_job("sync")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_visual_index_job, str(job["id"]), "sync")
    return job


@app.post("/api/admin/visual-search/retry-failed", status_code=202)
def admin_retry_visual_search_failures(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        job = schedule_visual_index_job("retry_failed")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_visual_index_job, str(job["id"]), "retry_failed")
    return job


@app.post("/api/admin/sync-embeddings")
def admin_sync_embeddings(
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
):
    """Đồng bộ lại embedding ảnh từ SQL Server và rebuild FAISS index."""
    synced = sync_product_image_embeddings(db)
    total = FaissProductIndex._index.ntotal if FaissProductIndex._index else 0
    return {
        "synced": synced,
        "total_indexed": total,
        "message": f"Đã đồng bộ {synced} sản phẩm thay đổi ảnh. FAISS index hiện có {total} vectors.",
    }


@app.post("/api/admin/rebuild-index")
def admin_rebuild_index(
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
):
    """Xóa và build lại toàn bộ FAISS index từ SQL Server."""
    FaissProductIndex.invalidate()
    total = FaissProductIndex.build_from_db(db)
    return {
        "total_indexed": total,
        "message": f"Đã rebuild FAISS index với {total} vectors từ SQL Server.",
    }
