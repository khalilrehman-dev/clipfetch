from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import yt_dlp
from yt_dlp.utils import DownloadError

Platform = Literal["tiktok", "instagram"]


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
    """Pick the best progressive non-watermarked TikTok format we can identify."""
    candidates = [
        f
        for f in formats
        if _is_video_format(f) and _has_audio(f) and not _is_probably_watermarked(f)
    ]
    if not candidates:
        return None
    return max(candidates, key=_format_score)


def _platform_from_info(info: dict[str, Any]) -> Platform:
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if "tiktok" in extractor:
        return "tiktok"
    if "instagram" in extractor:
        return "instagram"
    raise DownloaderError("The link did not resolve to a supported TikTok or Instagram video.")


def _has_downloadable_video(info: dict[str, Any]) -> bool:
    formats = info.get("formats") or []
    if any(_is_video_format(fmt) for fmt in formats):
        return True
    # Some extractors expose a direct video URL without a formats list.
    return bool(info.get("url") and info.get("vcodec") not in (None, "none"))


def _reject_unsupported_instagram_content(info: dict[str, Any]) -> None:
    # Carousels/multi-posts are deliberately excluded in the first release.
    entries = info.get("entries")
    if entries:
        raise DownloaderError(
            "Instagram carousel posts are not supported yet. Paste a single public Reel or video post."
        )
    if not _has_downloadable_video(info):
        raise DownloaderError(
            "This Instagram post does not contain a downloadable video. Image-only posts are not supported."
        )


def _safe_name(title: str | None, media_id: str | None, ext: str, platform: Platform) -> str:
    fallback = "instagram-video" if platform == "instagram" else "tiktok-video"
    raw = (title or fallback).strip()
    raw = re.sub(r"[^A-Za-z0-9._ -]+", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ._-")
    if not raw:
        raw = fallback
    raw = raw[:70]
    suffix = f"-{media_id}" if media_id else ""
    return f"{raw}{suffix}.{ext}"


def _thumbnail(info: dict[str, Any]) -> str | None:
    thumbnail = info.get("thumbnail")
    if thumbnail:
        return str(thumbnail)
    thumbs = info.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return None


def extract_metadata(url: str, max_duration_seconds: int) -> dict[str, Any]:
    info, platform = _extract_raw(url, max_duration_seconds=max_duration_seconds)
    formats = info.get("formats") or []

    if platform == "instagram":
        _reject_unsupported_instagram_content(info)
        clean = None
        default_title = "Instagram video"
        default_author = "Instagram creator"
    else:
        clean = choose_clean_format(formats)
        default_title = "TikTok video"
        default_author = "TikTok creator"

    duration = int(info.get("duration") or 0)
    return {
        "id": str(info.get("id") or ""),
        "platform": platform,
        "platform_label": "Instagram" if platform == "instagram" else "TikTok",
        "title": info.get("title") or info.get("description") or default_title,
        "description": info.get("description") or "",
        "author": info.get("uploader") or info.get("creator") or info.get("channel") or default_author,
        "duration": duration,
        "thumbnail": _thumbnail(info),
        "webpage_url": info.get("webpage_url") or url,
        "clean_available": platform == "tiktok" and clean is not None,
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
    # Resolve once so TikTok can deliberately select a clean stream and both
    # platforms can be validated before any server-side file is created.
    info, platform = _extract_raw(url, max_duration_seconds=max_duration_seconds)
    if platform == "instagram":
        _reject_unsupported_instagram_content(info)

    temp_dir = Path(tempfile.mkdtemp(prefix="snipivo-"))
    media_id = str(info.get("id") or "")
    title = info.get("title") or info.get("description")

    try:
        opts = _base_opts()
        opts["paths"] = {"home": str(temp_dir)}
        opts["outtmpl"] = str(temp_dir / "%(id)s.%(ext)s")

        if kind == "video-clean":
            if platform != "tiktok":
                raise CleanStreamUnavailable(
                    "The clean-stream option is only available for supported TikTok videos."
                )
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
            if platform == "instagram":
                # Prefer a ready-to-download progressive MP4. When Instagram
                # exposes separate streams, yt-dlp/FFmpeg can merge them.
                opts["format"] = (
                    "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo+bestaudio/best"
                )
            else:
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
            raise DownloaderError(_friendly_error(str(exc), platform)) from exc

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
            download_name=_safe_name(str(title) if title else None, media_id, target_ext, platform),
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _extract_raw(url: str, max_duration_seconds: int) -> tuple[dict[str, Any], Platform]:
    opts = _base_opts()
    opts["skip_download"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        # At this point the platform can usually be inferred from the URL, even
        # when the remote site rejects the extraction before metadata is returned.
        platform: Platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
        raise DownloaderError(_friendly_error(str(exc), platform)) from exc
    except Exception as exc:
        platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
        label = "Instagram" if platform == "instagram" else "TikTok"
        raise DownloaderError(f"{label} could not be reached for this link right now.") from exc

    if not info:
        raise DownloaderError("No video information was returned for this link.")

    platform = _platform_from_info(info)

    duration = int(info.get("duration") or 0)
    if duration and duration > max_duration_seconds:
        raise DownloaderError(
            f"This video is longer than the server limit of {max_duration_seconds // 60} minutes."
        )
    return info, platform


def _friendly_error(message: str, platform: Platform) -> str:
    lower = message.lower()
    label = "Instagram" if platform == "instagram" else "TikTok"

    if "private" in lower or "login" in lower or "sign in" in lower or "cookies" in lower:
        return f"This {label} post is private or requires login. Only public videos are supported."
    if (
        "not available" in lower
        or "video not found" in lower
        or "status code 10216" in lower
        or "404" in lower
    ):
        return f"This {label} video is unavailable, deleted, region-restricted, or not public."
    if "unsupported url" in lower:
        if platform == "instagram":
            return "That Instagram URL format is not supported. Use a public Reel or video-post link."
        return "That TikTok URL format is not supported."
    if "too many requests" in lower or "429" in lower or "rate-limit" in lower or "rate limit" in lower:
        return f"{label} is rate-limiting this server. Try again shortly."
    if platform == "instagram" and ("image" in lower or "photo" in lower):
        return "This Instagram post does not contain a downloadable video."
    return f"{label} could not provide this video right now. The link may be unavailable or temporarily blocked."
