from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import yt_dlp
from yt_dlp.utils import DownloadError

Platform = Literal["tiktok", "instagram"]
ContentType = Literal["video", "image", "carousel"]


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


@dataclass(frozen=True)
class ImagePostInfo:
    platform: Platform
    content_type: ContentType
    images: tuple[str, ...]
    title: str
    description: str
    author: str
    media_id: str
    webpage_url: str
    thumbnail: str | None


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MAX_IMAGE_ITEMS = int(os.getenv("MAX_IMAGE_ITEMS", "35"))
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(25 * 1024 * 1024)))
MAX_IMAGE_TOTAL_BYTES = int(os.getenv("MAX_IMAGE_TOTAL_BYTES", str(120 * 1024 * 1024)))


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
    raise DownloaderError("The link did not resolve to supported TikTok or Instagram media.")


def _has_downloadable_video(info: dict[str, Any]) -> bool:
    formats = info.get("formats") or []
    if any(_is_video_format(fmt) for fmt in formats):
        return True
    return bool(info.get("url") and info.get("vcodec") not in (None, "none"))


def _safe_stem(title: str | None, media_id: str | None, platform: Platform) -> str:
    fallback = "instagram-media" if platform == "instagram" else "tiktok-media"
    raw = (title or fallback).strip()
    raw = re.sub(r"[^A-Za-z0-9._ -]+", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ._-")
    if not raw:
        raw = fallback
    raw = raw[:70]
    suffix = f"-{media_id}" if media_id else ""
    return f"{raw}{suffix}"


def _safe_name(title: str | None, media_id: str | None, ext: str, platform: Platform) -> str:
    return f"{_safe_stem(title, media_id, platform)}.{ext}"


def _thumbnail(info: dict[str, Any]) -> str | None:
    thumbnail = info.get("thumbnail")
    if thumbnail:
        return str(thumbnail)
    thumbs = info.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return None


def _decode_url(value: str) -> str:
    value = html_lib.unescape(value)
    value = value.replace("\\u0026", "&").replace("\\/", "/")
    try:
        value = bytes(value, "utf-8").decode("unicode_escape") if "\\u" in value else value
    except UnicodeDecodeError:
        pass
    return value


def _unique_urls(urls: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        if not raw:
            continue
        url = _decode_url(str(raw)).strip()
        if not url.startswith("https://"):
            continue
        try:
            parsed = urllib.parse.urlparse(url)
            # Social CDNs often expose the same image in several sizes with
            # different query strings. Ignore the query when deduplicating so
            # one photo does not look like a multi-image carousel.
            identity = f"{(parsed.hostname or '').lower()}{parsed.path}"
        except ValueError:
            identity = url
        if identity in seen:
            continue
        seen.add(identity)
        out.append(url)
        if len(out) >= MAX_IMAGE_ITEMS:
            break
    return out


def _is_allowed_media_cdn(url: str, platform: Platform) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    if parsed.scheme != "https" or not host:
        return False
    if platform == "instagram":
        return host.endswith("cdninstagram.com") or host.endswith("fbcdn.net")
    return (
        host.endswith("tiktokcdn.com")
        or host.endswith("tiktokcdn-us.com")
        or host.endswith("ibytedtos.com")
        or host.endswith("muscdn.com")
        or host.endswith("byteimg.com")
    )


def _fetch_bytes(url: str, *, referer: str, max_bytes: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _BROWSER_UA,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": referer,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            length = int(response.headers.get("Content-Length") or 0)
            if length and length > max_bytes:
                raise DownloaderError("One of the images is too large for the server limit.")
            data = response.read(max_bytes + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DownloaderError("The image host could not be reached right now. Please try again.") from exc
    if len(data) > max_bytes:
        raise DownloaderError("One of the images is too large for the server limit.")
    if not content_type.startswith("image/"):
        raise DownloaderError("The source did not return a valid image file.")
    return data, content_type


def _fetch_text(url: str, *, referer: str | None = None) -> str:
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(6 * 1024 * 1024)
            return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DownloaderError("The public post could not be reached right now. Please try again.") from exc


def _extract_meta(html: str, property_name: str) -> str | None:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(property_name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return html_lib.unescape(match.group(1))
    return None


def _instagram_image_candidates(page_html: str) -> list[str]:
    # A top-level display_url normally represents the original media image for
    # a post/sidecar child. Prefer those over display_resources/image_versions
    # because those latter structures contain multiple resized copies of the
    # same photo.
    display_urls = [
        match.group(1)
        for match in re.finditer(
            r'"display_url"\s*:\s*"(https:[^"]+)"',
            page_html,
            flags=re.DOTALL,
        )
    ]
    display_urls = [
        url for url in _unique_urls(display_urls)
        if _is_allowed_media_cdn(url, "instagram")
    ]
    if display_urls:
        return display_urls

    og_image = _extract_meta(page_html, "og:image")
    if og_image and _is_allowed_media_cdn(_decode_url(og_image), "instagram"):
        return [_decode_url(og_image)]

    # Last-resort scan of known image CDNs. This is intentionally only used
    # when structured image fields are absent.
    candidates = re.findall(
        r'(https:(?:\\/|/){2}[^"\s<>]+?(?:cdninstagram\.com|fbcdn\.net)[^"\s<>]*)',
        page_html,
        flags=re.IGNORECASE,
    )
    return [url for url in _unique_urls(candidates) if _is_allowed_media_cdn(url, "instagram")]


def _tiktok_item_id(url: str) -> str | None:
    match = re.search(r"/(?:photo|video)/(\d+)", urllib.parse.urlparse(url).path)
    return match.group(1) if match else None


def _walk_image_urls(node: Any, out: list[str]) -> None:
    if len(out) >= MAX_IMAGE_ITEMS:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            key_lower = str(key).lower()
            if key_lower in {"urllist", "url_list"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("http"):
                        out.append(item)
                        break
            elif key_lower in {"display_url", "imageurl", "image_url"} and isinstance(value, str):
                out.append(value)
            else:
                _walk_image_urls(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_image_urls(item, out)


def _find_image_post_nodes(node: Any, out: list[Any]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in {"imagepost", "image_post"}:
                out.append(value)
            else:
                _find_image_post_nodes(value, out)
    elif isinstance(node, list):
        for item in node:
            _find_image_post_nodes(item, out)


def _tiktok_photo_candidates(url: str, page_html: str) -> list[str]:
    candidates: list[str] = []
    item_id = _tiktok_item_id(url)

    # Prefer TikTok's public item detail response for photo/slideshow posts.
    if item_id:
        api_url = f"https://www.tiktok.com/api/item/detail/?itemId={urllib.parse.quote(item_id)}"
        try:
            payload_text = _fetch_text(api_url, referer=url)
            payload = json.loads(payload_text)
            item_struct = ((payload.get("itemInfo") or {}).get("itemStruct") or {})
            image_post = item_struct.get("imagePost") or item_struct.get("image_post") or {}
            images = image_post.get("images") or []
            for image in images:
                if not isinstance(image, dict):
                    continue
                image_url = image.get("imageURL") or image.get("imageUrl") or image.get("image_url") or {}
                if isinstance(image_url, dict):
                    urls = image_url.get("urlList") or image_url.get("url_list") or []
                    if urls:
                        candidates.append(str(urls[0]))
                elif isinstance(image_url, str):
                    candidates.append(image_url)
        except (DownloaderError, json.JSONDecodeError, TypeError, ValueError):
            pass

    # Fallback to hydration JSON embedded in the public page.
    script_patterns = [
        r'<script[^>]+id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>',
        r'<script[^>]+id=["\']SIGI_STATE["\'][^>]*>(.*?)</script>',
    ]
    for pattern in script_patterns:
        match = re.search(pattern, page_html, flags=re.DOTALL | re.IGNORECASE)
        if not match:
            continue
        try:
            payload = json.loads(html_lib.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        image_nodes: list[Any] = []
        _find_image_post_nodes(payload, image_nodes)
        for image_node in image_nodes:
            found: list[str] = []
            _walk_image_urls(image_node, found)
            candidates.extend(found)

    if not candidates:
        candidates.extend(
            re.findall(
                r'(https:(?:\\/|/){2}[^"\s<>]+?(?:tiktokcdn(?:-us)?\.com|ibytedtos\.com|muscdn\.com|byteimg\.com)[^"\s<>]*)',
                page_html,
                flags=re.IGNORECASE,
            )
        )
    return [url for url in _unique_urls(candidates) if _is_allowed_media_cdn(url, "tiktok")]


def _resolve_public_images(url: str, platform: Platform) -> ImagePostInfo:
    page_html = _fetch_text(url)
    path = urllib.parse.urlparse(url).path.lower()
    if platform == "instagram":
        # Reels/TV routes are video-first. Do not mistake their poster image for
        # a downloadable photo when the video extractor is temporarily blocked.
        if path.startswith(("/reel/", "/reels/", "/tv/", "/share/reel/")):
            raise DownloaderError("This Instagram link is a video/Reel rather than a photo post.")
        if re.search(r'<meta[^>]+property=["\']og:video(?::[^"\']*)?["\']', page_html, re.I):
            raise DownloaderError("This Instagram post contains video rather than a photo post.")
        images = _instagram_image_candidates(page_html)
        title = _extract_meta(page_html, "og:title") or "Instagram photo"
        description = _extract_meta(page_html, "og:description") or ""
        author_match = re.search(r"@([A-Za-z0-9._]+)", title)
        author = author_match.group(1) if author_match else "Instagram creator"
        media_id_match = re.search(r"/(?:p|reel|reels|tv)/([^/?#]+)", urllib.parse.urlparse(url).path)
        media_id = media_id_match.group(1) if media_id_match else ""
    else:
        images = _tiktok_photo_candidates(url, page_html)
        title = _extract_meta(page_html, "og:title") or "TikTok photo post"
        description = _extract_meta(page_html, "og:description") or ""
        author_match = re.search(r"@([A-Za-z0-9._]+)", title)
        author = author_match.group(1) if author_match else "TikTok creator"
        media_id = _tiktok_item_id(url) or ""

    if not images:
        label = "Instagram" if platform == "instagram" else "TikTok"
        raise DownloaderError(
            f"This {label} post did not expose public image files. It may require login or the platform may be blocking this server."
        )

    content_type: ContentType = "image" if len(images) == 1 else "carousel"
    return ImagePostInfo(
        platform=platform,
        content_type=content_type,
        images=tuple(images),
        title=title,
        description=description,
        author=author,
        media_id=media_id,
        webpage_url=url,
        thumbnail=images[0],
    )


def _image_metadata(info: ImagePostInfo) -> dict[str, Any]:
    label = "Instagram" if info.platform == "instagram" else "TikTok"
    return {
        "id": info.media_id,
        "platform": info.platform,
        "platform_label": label,
        "content_type": info.content_type,
        "title": info.title,
        "description": info.description,
        "author": info.author,
        "duration": 0,
        "thumbnail": info.thumbnail,
        "webpage_url": info.webpage_url,
        "clean_available": False,
        "clean_format_id": None,
        "clean_resolution": None,
        "formats_count": 0,
        "image_count": len(info.images),
        "has_images": True,
    }


def extract_metadata(url: str, max_duration_seconds: int) -> dict[str, Any]:
    platform: Platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
    try:
        info, platform = _extract_raw(url, max_duration_seconds=max_duration_seconds)
    except DownloaderError as video_error:
        # yt-dlp is intentionally video-centric for some social image posts.
        # If video extraction fails, attempt a public-page image resolver.
        try:
            return _image_metadata(_resolve_public_images(url, platform))
        except DownloaderError as image_error:
            # Preserve authoritative access/rate-limit errors. For a normal
            # no-video-formats failure, surface the image resolver result.
            lower = str(video_error).lower()
            if "private or requires login" in lower or "rate-limiting" in lower:
                raise video_error
            raise image_error

    formats = info.get("formats") or []
    entries = info.get("entries") or []
    if entries and not _has_downloadable_video(info):
        try:
            return _image_metadata(_resolve_public_images(url, platform))
        except DownloaderError:
            pass

    if not _has_downloadable_video(info):
        return _image_metadata(_resolve_public_images(url, platform))

    if platform == "instagram":
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
        "content_type": "video",
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
        "image_count": 0,
        "has_images": False,
    }


def _image_ext(content_type: str, url: str) -> str:
    mapping = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/avif": "avif",
        "image/gif": "gif",
    }
    if content_type in mapping:
        return mapping[content_type]
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".")
    return suffix if suffix in {"jpg", "jpeg", "png", "webp", "avif", "gif"} else "jpg"


def _download_image_post(url: str, kind: str, platform: Platform) -> DownloadArtifact:
    image_info = _resolve_public_images(url, platform)
    if kind == "image-single":
        selected = image_info.images[:1]
    elif kind == "images-zip":
        selected = image_info.images
    else:
        raise DownloaderError("Unknown image download type.")

    temp_dir = Path(tempfile.mkdtemp(prefix="snipivo-images-"))
    stem = _safe_stem(image_info.title, image_info.media_id, platform)
    total_bytes = 0
    downloaded: list[tuple[Path, str]] = []
    try:
        for index, image_url in enumerate(selected, start=1):
            if not _is_allowed_media_cdn(image_url, platform):
                continue
            data, content_type = _fetch_bytes(image_url, referer=url, max_bytes=MAX_IMAGE_BYTES)
            total_bytes += len(data)
            if total_bytes > MAX_IMAGE_TOTAL_BYTES:
                raise DownloaderError("This image post is too large for the server download limit.")
            ext = _image_ext(content_type, image_url)
            path = temp_dir / f"image-{index:02d}.{ext}"
            path.write_bytes(data)
            downloaded.append((path, content_type))

        if not downloaded:
            raise DownloaderError("The post was resolved, but no image file could be downloaded.")

        if kind == "image-single":
            path, content_type = downloaded[0]
            ext = path.suffix.lower().lstrip(".") or "jpg"
            return DownloadArtifact(
                path=path,
                temp_dir=temp_dir,
                media_type=content_type,
                download_name=f"{stem}.{ext}",
            )

        zip_path = temp_dir / f"{stem}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, _content_type in downloaded:
                archive.write(path, arcname=path.name)
        return DownloadArtifact(
            path=zip_path,
            temp_dir=temp_dir,
            media_type="application/zip",
            download_name=f"{stem}-images.zip",
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def download_media(url: str, kind: str, max_duration_seconds: int) -> DownloadArtifact:
    platform: Platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
    if kind in {"image-single", "images-zip"}:
        return _download_image_post(url, kind, platform)

    info, platform = _extract_raw(url, max_duration_seconds=max_duration_seconds)
    if not _has_downloadable_video(info):
        raise DownloaderError("This post contains images rather than a downloadable video. Choose the image download option.")

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
        platform: Platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
        raise DownloaderError(_friendly_error(str(exc), platform)) from exc
    except Exception as exc:
        platform = "instagram" if "instagram.com" in url.lower() or "instagr.am" in url.lower() else "tiktok"
        label = "Instagram" if platform == "instagram" else "TikTok"
        raise DownloaderError(f"{label} could not be reached for this link right now.") from exc

    if not info:
        raise DownloaderError("No media information was returned for this link.")

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
        return f"This {label} post is private or requires login. Only public media is supported."
    if (
        "not available" in lower
        or "video not found" in lower
        or "status code 10216" in lower
        or "404" in lower
    ):
        return f"This {label} post is unavailable, deleted, region-restricted, or not public."
    if "unsupported url" in lower:
        if platform == "instagram":
            return "That Instagram URL format is not supported. Use a public Reel or post link."
        return "That TikTok URL format is not supported."
    if "too many requests" in lower or "429" in lower or "rate-limit" in lower or "rate limit" in lower:
        return f"{label} is rate-limiting this server. Try again shortly."
    if "no video formats" in lower or "image" in lower or "photo" in lower:
        return f"This {label} post may contain photos. Snipivo will try the public image resolver."
    return f"{label} could not provide this media right now. The link may be unavailable or temporarily blocked."
