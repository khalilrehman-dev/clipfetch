# Snipivo

A FastAPI + yt-dlp downloader for **permitted public TikTok and Instagram media**.

## V1.6 quality + preview upgrade

V1.6 builds on V1.5 with a clearer resolved-media experience and user-selectable download quality:

- Proper platform + media-type preview badges after resolving a link.
- Available video choices: Best, 1080p, and 720p when the public source exposes them.
- MP3 bitrate choices: 128, 192, and 320 kbps.
- Approximate file-size hints when metadata is available.
- Carousel image count shown before ZIP download.
- Quality-aware preparation status and GA4 events.
- Actual prepared file size returned by the API when available.

Existing media support remains:

- TikTok public videos: clean stream when available, MP4, MP3.
- Instagram public Reels/video posts: MP4, MP3.
- Instagram public single-image posts: download the available image.
- Instagram public image carousels: package supported exposed images into one ZIP.
- TikTok public photo-mode posts/slideshows: package supported exposed images into one ZIP.
- Automatic platform and media-type detection.
- One-click prepared-download handoff remains in place; no second "tap to save" step.
- V1.4 cache busting/no-cache headers remain in place for mobile browsers.

Image support is intentionally **best effort**. Instagram and TikTok can change what their public pages expose, require login for some posts, or rate-limit the server. Snipivo does not request social-account passwords/cookies to bypass access controls.

## Quick start with Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

Health check:

```text
http://localhost:8000/api/health
```

## Run locally without Docker

Requirements:

- Python 3.11+
- FFmpeg on PATH

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API

### `POST /api/resolve`

```json
{"url":"https://www.tiktok.com/@creator/video/123"}
```

or

```json
{"url":"https://www.instagram.com/p/ABC123/"}
```

The response includes `platform`, `content_type` (`video`, `image`, or `carousel`), metadata, `image_count` when applicable, and quality/size hints for videos.

### `POST /api/prepare-download`

Supported `kind` values:

- `video-clean` - TikTok video only, when a clean public stream exists.
- `video-best` - MP4 using `video_quality`: `best`, `1080`, or `720`.
- `audio-mp3` - MP3 audio using `audio_bitrate`: `128`, `192`, or `320`.
- `image-single` - a supported single image.
- `images-zip` - supported images packaged in one ZIP.

## Environment variables

- `MAX_DURATION_SECONDS` - maximum video duration, default `1200`.
- `INFO_CONCURRENCY` - metadata resolutions, default `8`.
- `DOWNLOAD_CONCURRENCY` - simultaneous media jobs, default `3`.
- `RATE_LIMIT_REQUESTS` - API requests per rate-limit window/IP, default `30`.
- `RATE_LIMIT_WINDOW_SECONDS` - default `60`.
- `PREPARED_TTL_SECONDS` - prepared download lifetime, default `300`.
- `MAX_IMAGE_ITEMS` - maximum image count per post, default `35`.
- `MAX_IMAGE_BYTES` - maximum bytes per image, default `25 MiB`.
- `MAX_IMAGE_TOTAL_BYTES` - maximum total image bytes before ZIP, default `120 MiB`.
- `ENABLE_DOCS=1` - expose FastAPI docs at `/api/docs`.

## Analytics

The frontend uses GA4 measurement ID `G-EDY1BTVYY9` and avoids intentionally sending submitted post URLs/titles in custom event parameters.

Video events include:

- `media_resolved`
- `video_resolved`
- `download_clean`
- `download_mp4`
- `download_mp3`
- `download_instagram_mp4`
- `download_instagram_mp3`

Image events include:

- `image_post_resolved`
- `download_instagram_image`
- `download_instagram_images_zip`
- `download_tiktok_image`
- `download_tiktok_images_zip`

## SEO / IndexNow

The sitemap includes the existing TikTok/Instagram video pages plus:

- `/instagram-photo-downloader/`
- `/tiktok-photo-downloader/`

Use IndexNow only after a page actually changes; do not repeatedly submit unchanged URLs.

## Safety / access boundaries

Snipivo accepts only allow-listed TikTok/Instagram post hosts and does not act as a general URL fetcher. Remote image downloads are additionally restricted to known TikTok/Instagram image CDN host families. Private/login-only content is not intentionally bypassed.
