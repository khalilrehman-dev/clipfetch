from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from .downloader import CleanStreamUnavailable, DownloaderError, download_media, extract_metadata
from .security import validate_tiktok_url


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "1200"))
INFO_CONCURRENCY = int(os.getenv("INFO_CONCURRENCY", "8"))
DOWNLOAD_CONCURRENCY = int(os.getenv("DOWNLOAD_CONCURRENCY", "3"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

info_semaphore = asyncio.Semaphore(INFO_CONCURRENCY)
download_semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
request_buckets: dict[str, Deque[float]] = defaultdict(deque)


class ResolveRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


app = FastAPI(
    title="Snipivo",
    version="1.0.0",
    docs_url="/api/docs" if os.getenv("ENABLE_DOCS", "0") == "1" else None,
    redoc_url=None,
)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client_ip = forwarded or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        bucket = request_buckets[client_ip]
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again in a moment."},
            )
        bucket.append(now)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "snipivo"}


@app.post("/api/resolve")
async def resolve_video(body: ResolveRequest):
    try:
        url = validate_tiktok_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        async with info_semaphore:
            info = await run_in_threadpool(extract_metadata, url, MAX_DURATION_SECONDS)
        return info
    except DownloaderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/download")
async def download(
    url: str = Query(min_length=8, max_length=2048),
    kind: str = Query(pattern="^(video-clean|video-best|audio-mp3)$"),
):
    try:
        clean_url = validate_tiktok_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        async with download_semaphore:
            artifact = await run_in_threadpool(
                download_media,
                clean_url,
                kind,
                MAX_DURATION_SECONDS,
            )
    except CleanStreamUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DownloaderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        path=artifact.path,
        media_type=artifact.media_type,
        filename=artifact.download_name,
        background=BackgroundTask(shutil.rmtree, artifact.temp_dir, True),
        headers={"Cache-Control": "private, no-store"},
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
