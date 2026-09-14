from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yt_dlp
from yt_dlp.utils import DownloadError


class DownloaderError(RuntimeError):
    pass


class CleanStreamUnavailable(DownloaderError):
    pass


@dataclass(frozen=True)
class DownloadArtifact:
    path: Path
    temp_dir: Path
    media_type: str
    download_name: str


def _base_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": int(os.getenv("YTDLP_SOCKET_TIMEOUT", "20")),
        "retries": int(os.getenv("YTDLP_RETRIES", "3")),
        "fragment_retries": int(os.getenv("YTDLP_FRAGMENT_RETRIES", "3")),
        "concurrent_fragment_downloads": 2,
        "restrictfilenames": True,
        "nocheckcertificate": False,
        "cachedir": False,
    }


def _is_video_format(fmt: dict[str, Any]) -> bool:
    return fmt.get("vcodec") not in (None, "none")


def _has_audio(fmt: dict[str, Any]) -> bool:
    return fmt.get("acodec") not in (None, "none")


def _is_probably_watermarked(fmt: dict[str, Any]) -> bool:
    fid = str(fmt.get("format_id") or "").lower()
    note = str(fmt.get("format_note") or "").lower()
    url = str(fmt.get("url") or "").lower()

    # yt-dlp's TikTok extractor commonly calls the branded download stream
    # "download" and marks it as "watermarked". TikTok CDN watermark URLs also
    # frequently contain /logo/ or logo_type=tiktok. These signals are used only
    # to avoid falsely labelling a stream as clean.
    if fid == "download":
        return True
    if "watermark" in note:
        return True
    if "/logo/" in url or "logo_type=tiktok" in url:
        return True
    return False


def _format_score(fmt: dict[str, Any]) -> tuple[int, float, int, int]:
    ext_bonus = 1 if str(fmt.get("ext") or "").lower() == "mp4" else 0
    height = int(fmt.get("height") or 0)
    tbr = float(fmt.get("tbr") or 0.0)
    size = int(fmt.get("filesize") or fmt.get("filesize_approx") or 0)
    return (ext_bonus, height, tbr, size)


def choose_clean_format(formats: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the best progressive non-watermarked format we can identify."""
    candidates = [
        f
        for f in formats
        if _is_video_format(f) and _has_audio(f) and not _is_probably_watermarked(f)
    ]
    if not candidates:
        return None
    return max(candidates, key=_format_score)


def _safe_name(title: str | None, video_id: str | None, ext: str) -> str:
    raw = (title or "tiktok-video").strip()
    raw = re.sub(r"[^A-Za-z0-9._ -]+", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ._-")
    if not raw:
        raw = "tiktok-video"
    raw = raw[:70]
    suffix = f"-{video_id}" if video_id else ""
    return f"{raw}{suffix}.{ext}"


def extract_metadata(url: str, max_duration_seconds: int) -> dict[str, Any]:
    opts = _base_opts()
    opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise DownloaderError(_friendly_error(str(exc))) from exc
    except Exception as exc:  # keep client-facing errors generic
        raise DownloaderError("TikTok could not be reached for this link right now.") from exc

    if not info:
        raise DownloaderError("No video information was returned for this TikTok link.")

    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if "tiktok" not in extractor:
        raise DownloaderError("The link did not resolve to a TikTok video.")

    duration = int(info.get("duration") or 0)
    if duration and duration > max_duration_seconds:
        raise DownloaderError(
            f"This video is longer than the server limit of {max_duration_seconds // 60} minutes."
        )

    formats = info.get("formats") or []
    clean = choose_clean_format(formats)

    thumbnail = info.get("thumbnail")
    if not thumbnail:
        thumbs = info.get("thumbnails") or []
        if thumbs:
            thumbnail = thumbs[-1].get("url")

    return {
        "id": str(info.get("id") or ""),
        "title": info.get("title") or info.get("description") or "TikTok video",
        "description": info.get("description") or "",
        "author": info.get("uploader") or info.get("creator") or info.get("channel") or "TikTok creator",
        "duration": duration,
        "thumbnail": thumbnail,
        "webpage_url": info.get("webpage_url") or url,
        "clean_available": clean is not None,
        "clean_format_id": clean.get("format_id") if clean else None,
        "clean_resolution": (
            f"{clean.get('width')}x{clean.get('height')}"
            if clean and clean.get("width") and clean.get("height")
            else (clean.get("resolution") if clean else None)
        ),
        "formats_count": len(formats),
    }


def download_media(
    url: str,
    kind: str,
    max_duration_seconds: int,
) -> DownloadArtifact:
    # Resolve once so we can deliberately select a clean stream rather than
    # depending on a site's changing default format order.
    info = _extract_raw(url, max_duration_seconds=max_duration_seconds)
    temp_dir = Path(tempfile.mkdtemp(prefix="clipfetch-"))
    video_id = str(info.get("id") or "")
    title = info.get("title") or info.get("description") or "tiktok-video"

    try:
        opts = _base_opts()
        opts["paths"] = {"home": str(temp_dir)}
        opts["outtmpl"] = str(temp_dir / "%(id)s.%(ext)s")

        if kind == "video-clean":
            clean = choose_clean_format(info.get("formats") or [])
            if not clean:
                raise CleanStreamUnavailable(
                    "TikTok did not expose a non-watermarked public stream for this video."
                )
            opts["format"] = str(clean.get("format_id"))
            opts["merge_output_format"] = "mp4"
            target_ext = "mp4"
            media_type = "video/mp4"
        elif kind == "video-best":
            # Prefer a progressive MP4 but allow yt-dlp to fall back when TikTok
            # exposes a different set of formats for a particular post.
            opts["format"] = "best[ext=mp4]/best"
            opts["merge_output_format"] = "mp4"
            target_ext = "mp4"
            media_type = "video/mp4"
        elif kind == "audio-mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
            target_ext = "mp3"
            media_type = "audio/mpeg"
        else:
            raise DownloaderError("Unknown download type.")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except DownloadError as exc:
            raise DownloaderError(_friendly_error(str(exc))) from exc

        files = [
            p
            for p in temp_dir.iterdir()
            if p.is_file() and not p.name.endswith((".part", ".ytdl"))
        ]
        if not files:
            raise DownloaderError("The video was resolved, but the media file could not be downloaded.")

        # FFmpeg can leave intermediate files. Prefer the requested extension,
        # then choose the largest remaining media file.
        preferred = [p for p in files if p.suffix.lower() == f".{target_ext}"]
        final_path = max(preferred or files, key=lambda p: p.stat().st_size)

        return DownloadArtifact(
            path=final_path,
            temp_dir=temp_dir,
            media_type=media_type,
            download_name=_safe_name(str(title), video_id, target_ext),
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _extract_raw(url: str, max_duration_seconds: int) -> dict[str, Any]:
    opts = _base_opts()
    opts["skip_download"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise DownloaderError(_friendly_error(str(exc))) from exc

    if not info:
        raise DownloaderError("No video information was returned for this TikTok link.")

    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if "tiktok" not in extractor:
        raise DownloaderError("The link did not resolve to a TikTok video.")

    duration = int(info.get("duration") or 0)
    if duration and duration > max_duration_seconds:
        raise DownloaderError(
            f"This video is longer than the server limit of {max_duration_seconds // 60} minutes."
        )
    return info


def _friendly_error(message: str) -> str:
    lower = message.lower()
    if "private" in lower or "login" in lower or "sign in" in lower:
        return "This video is private or requires a TikTok login. Only public videos are supported."
    if "not available" in lower or "video not found" in lower or "status code 10216" in lower:
        return "This TikTok video is unavailable, deleted, region-restricted, or not public."
    if "unsupported url" in lower:
        return "That TikTok URL format is not supported."
    if "too many requests" in lower or "429" in lower:
        return "TikTok is rate-limiting this server. Try again shortly."
    return "TikTok could not provide this video right now. The link may be unavailable or temporarily blocked."
