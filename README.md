# Snipivo

A full-stack TikTok downloader for **public videos that the user is allowed to save**.

## What it does

- Paste a TikTok full URL or common TikTok short/share URL.
- Resolve public video metadata and thumbnail.
- Prefer a progressive public stream that is **not identified as watermarked**.
- Offer a best-available MP4 fallback.
- Offer MP3 extraction through FFmpeg.
- Refuse private/login-only content rather than using TikTok account cookies.
- Delete temporary media after each response.
- Restrict server-side fetching to TikTok hostnames.
- Include basic API rate limiting and download concurrency limits.

> Important: TikTok changes its delivery layer regularly. No third-party downloader can honestly guarantee every public post will work forever. Keep `yt-dlp` current, and test after TikTok changes. This project intentionally does not bypass private videos, login gates, DRM, or access controls.

## Quick start with Docker

Requirements: Docker Desktop / Docker Engine.

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/api/health
```

## Run locally without Docker

Requirements:

- Python 3.11+
- FFmpeg installed and available on PATH

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Keeping TikTok extraction current

The project requires yt-dlp 2026.08.19 or newer and installs its `curl-cffi` impersonation extra. Update it when TikTok changes:

```bash
pip install -U --pre "yt-dlp[default,curl-cffi]"
```

For Docker, rebuild after changing `requirements.txt`:

```bash
docker compose build --no-cache
docker compose up -d
```

## API

### `POST /api/resolve`

Body:

```json
{"url":"https://www.tiktok.com/@creator/video/123"}
```

Returns video metadata plus `clean_available`.

### `GET /api/download`

Parameters:

- `url` — TikTok URL
- `kind` — `video-clean`, `video-best`, or `audio-mp3`

Example:

```text
/api/download?kind=video-clean&url=https%3A%2F%2Fwww.tiktok.com%2F...
```

## Production deployment

Recommended layout:

```text
Internet
  -> Cloudflare / CDN / WAF
  -> Nginx or Caddy (HTTPS, request limits)
  -> Snipivo Docker container
```

For a public service, also add:

- Persistent distributed rate limiting (Redis) if running multiple replicas.
- Abuse monitoring and bandwidth limits.
- A privacy policy and terms page.
- Copyright/takedown contact information appropriate to your jurisdiction.
- Server metrics and error monitoring.
- A queue/object-storage design if traffic becomes high enough that proxying downloads through one app server is expensive.

## Environment variables

Copy `.env.example` and tune as needed.

- `MAX_DURATION_SECONDS` — maximum video duration (default 1200)
- `INFO_CONCURRENCY` — simultaneous metadata resolutions (default 8)
- `DOWNLOAD_CONCURRENCY` — simultaneous media jobs (default 3)
- `RATE_LIMIT_REQUESTS` — API requests per window/IP (default 30)
- `RATE_LIMIT_WINDOW_SECONDS` — rate-limit window (default 60)
- `ENABLE_DOCS=1` — expose FastAPI Swagger docs at `/api/docs`

## Clean-stream logic

TikTok often exposes more than one media format. The project does **not** edit video frames to erase a watermark. Instead it selects a public stream that is not labelled or signalled as watermarked. If only a branded stream is available, the UI disables the "Without watermark" button.

## Analytics

The production frontend includes Google Analytics 4 measurement ID `G-EDY1BTVYY9`. In addition to standard page-view/enhanced-measurement data, the frontend emits these custom events without sending TikTok URLs, creator names, or other video metadata to Analytics:

- `video_resolved`
- `download_clean`
- `download_mp4`
- `download_mp3`
- `download_failed` (currently records resolve-stage failures)

Before promoting the site broadly, publish an appropriate privacy/cookie notice and configure consent handling where legally required.

## Trust, legal, and SEO pages

The production frontend includes these public pages:

- `/about/`
- `/faq/`
- `/privacy/`
- `/terms/`
- `/copyright/`
- `/contact/`

The sitemap contains all public pages and `robots.txt` points search engines to `https://snipivo.online/sitemap.xml`. The public contact address used by the pages is `support@snipivo.online`; configure that address as a working mailbox or forwarding alias before promoting the site.

For EEA/UK ad monetization later, configure an appropriate consent-management solution before enabling personalized advertising. Google AdSense may require a Google-certified CMP depending on audience and product configuration.


## SEO landing pages

This release includes indexable, canonical guide pages for:

- `/guides/`
- `/tiktok-video-downloader/`
- `/tiktok-video-downloader-without-watermark/`
- `/tiktok-to-mp3/`
- `/download-tiktok-video-iphone/`
- `/download-tiktok-video-android/`

The pages are linked internally from the homepage, use the existing GA4 tag, and are included in `sitemap.xml`.
