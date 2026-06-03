"""FastAPI application entry point.

Serves the REST API, the live WebSocket, and the static dashboard — one
deployable unit (backend + frontend) as decided for this challenge.

Startup is non-blocking: external services (PostgreSQL, Redis) are optional and
their unavailability will not prevent the app from starting. Health checks report
the actual status.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.db import Database
from backend.routers import api, ws

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Store Intelligence System",
    description="AI-powered CCTV store analytics — Purplle Tech Challenge 2026",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)
app.include_router(ws.router)


# Global flag to track startup completion
_schema_initialized = False


@app.on_event("startup")
async def _startup() -> None:
    """Non-blocking startup: attempt schema init but don't wait for it."""
    global _schema_initialized
    try:
        # Try to init schema with 3-second timeout
        db = Database(connect_timeout=3)
        success = db.init_schema(suppress_errors=True)
        if success:
            _schema_initialized = True
            logger.info("[api] schema initialized")
        else:
            logger.warning("[api] schema init deferred: PostgreSQL unavailable at startup")
            # Schedule retry in background
            asyncio.create_task(_retry_schema_init())
    except Exception as e:
        logger.warning(f"[api] startup warning: {e}")


async def _retry_schema_init(max_retries: int = 5, delay: int = 5) -> None:
    """Background task to retry schema initialization."""
    global _schema_initialized
    if _schema_initialized:
        return
    
    for attempt in range(1, max_retries + 1):
        await asyncio.sleep(delay)
        try:
            db = Database(connect_timeout=3)
            success = db.init_schema(suppress_errors=True)
            if success:
                _schema_initialized = True
                logger.info("[api] schema initialized (background retry)")
                return
        except Exception:
            pass
        logger.debug(f"[api] schema init retry {attempt}/{max_retries} failed, retrying...")


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/analyze")


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/journey")
def journey() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "journey.html")


@app.get("/business")
def business():
    return FileResponse(FRONTEND_DIR / "business.html")


_analysis_running = False

def run_analysis_in_background(target_path: Path):
    global _analysis_running
    _analysis_running = True
    try:
        from pipeline.run_lite import process_video
        process_video(str(target_path), max_frames=300)
    except Exception as e:
        logger.error(f"[background-analysis] error: {e}")
    finally:
        _analysis_running = False

@app.post("/upload-video")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    upload_dir = Path("data/videos")
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / "uploaded.mp4"
    content = await file.read()
    target_path.write_bytes(content)

    background_tasks.add_task(run_analysis_in_background, target_path)

    return {"status": "ok", "video": "/tracked_store.mp4"}

@app.get("/api/analysis-status")
def analysis_status() -> dict:
    from pipeline.run_lite import _run_progress
    return _run_progress


@app.get("/analyze")
def analyze() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "analyze.html")


@app.get("/tracked_store.mp4")
def tracked_video() -> FileResponse:
    video_path = Path("data/output/tracked_store.mp4")
    return FileResponse(video_path, media_type="video/mp4")


@app.get("/test.mp4")
def get_test_video() -> FileResponse:
    return FileResponse("test.mp4", media_type="video/mp4")


# static assets (css/js) served under /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
