# Snipivo

## V1.4 cache-busting fix

V1.4 forces browsers, including iPhone Safari/WebKit, to fetch the current frontend after deployment. The app now versions critical CSS/JS URLs and disables caching for HTML, `app.js`, and `styles.css`. This prevents old download logic from surviving across releases.


A FastAPI + yt-dlp downloader for **permitted public TikTok and Instagram videos**.

## What it does

- Accept TikTok full URLs and common TikTok short/share URLs.
- Accept public Instagram Reels and single public Instagram video-post URLs.
- Detect the platform automatically.
- Resolve public video metadata and thumbnail.
- For TikTok, offer a clean public stream when one can be identified, plus best-available MP4 and MP3.
- For Instagram, offer best-available MP4 and MP3 for supported public video posts/Reels.
- Refuse private/login-only content rather than asking for social-account credentials or cookies.
- Reject Instagram profiles, stories, image-only posts, and carousels in this release.
- Delete temporary media after each response.
- Restrict server-side fetching to a narrow allow-list of TikTok and Instagram hostnames.
- Include API rate limiting, download concurrency limits, and repeated-click protection in the frontend.

> Important: TikTok and Instagram change their delivery layers and anti-bot systems regularly. No third-party downloader can guarantee every public post will work forever. Keep `yt-dlp` current and test after platform changes. Snipivo intentionally does not bypass private posts, login gates, DRM, or access controls.

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

## Keeping extraction current

The project requires yt-dlp 2026.08.19 or newer and installs its `curl-cffi` impersonation extra.

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

TikTok example:

```json
{"url":"https://www.tiktok.com/@creator/video/123"}
```

Instagram example:

```json
{"url":"https://www.instagram.com/reel/ABC123/"}
```

The response includes `platform`, `platform_label`, video metadata, and TikTok `clean_available` information.

### `GET /api/download`

Parameters:

- `url` — supported TikTok or Instagram video URL
- `kind` — `video-clean`, `video-best`, or `audio-mp3`

`video-clean` is TikTok-only. Instagram supports `video-best` and `audio-mp3`.

## Production deployment

Recommended layout:

```text
Internet
  -> Cloudflare / CDN / WAF
  -> Nginx or Caddy (HTTPS, request limits)
  -> Snipivo Docker container
```

For a public service, also consider:

- Persistent distributed rate limiting (Redis) if running multiple replicas.
- Abuse monitoring and bandwidth limits.
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

TikTok often exposes more than one media format. Snipivo does **not** edit video frames to erase a watermark. It only labels a TikTok option as clean when the public format signals indicate a non-watermarked stream. Instagram does not show a separate "Without watermark" button.

## Analytics

The production frontend includes Google Analytics 4 measurement ID `G-EDY1BTVYY9`. Custom events do not intentionally include submitted URLs, creator names, or video titles.

TikTok/general events:

- `video_resolved` with a `platform` parameter
- `download_clean`
- `download_mp4`
- `download_mp3`
- `download_failed`

Instagram-specific events:

- `instagram_resolved`
- `download_instagram_mp4`
- `download_instagram_mp3`

## Trust, legal, SEO, and IndexNow

The production frontend includes About, FAQ, Privacy, Terms, Copyright, Contact, and guide pages. The sitemap includes the TikTok pages plus:

- `/instagram-video-downloader/`
- `/instagram-reels-downloader/`

The IndexNow key file and submission helper are included without removing the working frontend assets:

```bash
python scripts/submit_indexnow.py --url https://snipivo.online/instagram-video-downloader/
python scripts/submit_indexnow.py --url https://snipivo.online/instagram-reels-downloader/
```

Do not repeatedly submit unchanged URLs.

## V1.2 mobile download handoff

The download flow now prepares files through `/api/prepare-download` and hands them to the browser using a short-lived `/api/prepared-download/{token}` URL. This replaces the old hidden-iframe handoff, which could appear stuck on iPhone/iPad Safari. iOS users see a clear **Ready - tap to save** state after preparation; desktop and Android attempt the handoff automatically.

