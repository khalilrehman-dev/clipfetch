from __future__ import annotations

import asyncio
import os
import secrets
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
from .security import validate_media_url


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


class PrepareDownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    kind: str = Field(pattern=r"^(video-clean|video-best|audio-mp3)$")


PREPARED_TTL_SECONDS = int(os.getenv("PREPARED_TTL_SECONDS", "300"))
prepared_downloads: dict[str, tuple[object, float]] = {}


def _cleanup_expired_prepared() -> None:
    now = time.monotonic()
    expired = [
        token for token, (_artifact, created) in prepared_downloads.items()
        if now - created > PREPARED_TTL_SECONDS
    ]
    for token in expired:
        artifact, _created = prepared_downloads.pop(token, (None, 0.0))
        if artifact is not None:
            shutil.rmtree(artifact.temp_dir, ignore_errors=True)


app = FastAPI(
    title="Snipivo",
    version="1.2.0",
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
    return {"ok": True, "service": "snipivo", "platforms": ["tiktok", "instagram"]}


@app.post("/api/resolve")
async def resolve_video(body: ResolveRequest):
    try:
        url, platform = validate_media_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        async with info_semaphore:
            info = await run_in_threadpool(extract_metadata, url, MAX_DURATION_SECONDS)
        # Keep the URL-derived platform only as a consistency check. The
        # downloader also verifies the actual extractor returned by yt-dlp.
        if info.get("platform") != platform:
            raise DownloaderError("The link resolved to an unexpected platform.")
        return info
    except DownloaderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/prepare-download")
async def prepare_download(body: PrepareDownloadRequest):
    try:
        clean_url, platform = validate_media_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if platform == "instagram" and body.kind == "video-clean":
        raise HTTPException(
            status_code=400,
            detail="The clean-stream option is only available for supported TikTok videos.",
        )

    _cleanup_expired_prepared()

    try:
        async with download_semaphore:
            artifact = await run_in_threadpool(
                download_media,
                clean_url,
                body.kind,
                MAX_DURATION_SECONDS,
            )
    except CleanStreamUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DownloaderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    token = secrets.token_urlsafe(24)
    prepared_downloads[token] = (artifact, time.monotonic())
    return {
        "ok": True,
        "download_url": f"/api/prepared-download/{token}",
        "filename": artifact.download_name,
        "media_type": artifact.media_type,
    }


@app.get("/api/prepared-download/{token}")
async def prepared_download(token: str):
    _cleanup_expired_prepared()
    item = prepared_downloads.pop(token, None)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail="This prepared download expired or was already used. Prepare it again.",
        )

    artifact, _created = item
    return FileResponse(
        path=artifact.path,
        media_type=artifact.media_type,
        filename=artifact.download_name,
        background=BackgroundTask(shutil.rmtree, artifact.temp_dir, True),
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/download")
async def download(
    url: str = Query(min_length=8, max_length=2048),
    kind: str = Query(pattern="^(video-clean|video-best|audio-mp3)$"),
):
    try:
        clean_url, platform = validate_media_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if platform == "instagram" and kind == "video-clean":
        raise HTTPException(
            status_code=400,
            detail="The clean-stream option is only available for supported TikTok videos.",
        )

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
