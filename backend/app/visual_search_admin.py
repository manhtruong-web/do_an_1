"""Single-process background indexing coordinator for the admin dashboard."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .database import SessionLocal
from .visual_search import VisualSearchEngine

logger = logging.getLogger(__name__)
_job_lock = threading.Lock()
_job: dict[str, Any] = {"status": "idle"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_visual_index_job() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)


def schedule_visual_index_job(mode: str) -> dict[str, Any]:
    global _job
    with _job_lock:
        if _job.get("status") in {"queued", "running"}:
            raise RuntimeError("An index job is already running.")
        _job = {
            "id": str(uuid.uuid4()),
            "mode": mode,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        return dict(_job)


def run_visual_index_job(job_id: str, mode: str) -> None:
    global _job
    with _job_lock:
        if _job.get("id") != job_id or _job.get("status") != "queued":
            return
        _job["status"] = "running"
        _job["started_at"] = _utc_now()

    try:
        if SessionLocal is None:
            raise RuntimeError("SQL Server is not configured.")
        VisualSearchEngine.invalidate()
        with SessionLocal() as db:
            result = VisualSearchEngine.build_from_db(db)
        with _job_lock:
            if _job.get("id") == job_id:
                _job["status"] = "completed"
                _job["result"] = result
                _job["finished_at"] = _utc_now()
    except Exception as exc:
        logger.exception("Visual search index job failed (%s)", mode)
        with _job_lock:
            if _job.get("id") == job_id:
                _job["status"] = "failed"
                _job["error"] = type(exc).__name__
                _job["finished_at"] = _utc_now()
