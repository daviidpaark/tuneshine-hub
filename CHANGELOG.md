# Changelog

All notable changes to the `tuneshine-hub` central service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.1] - 2026-08-30

### Added
- **Heartbeat Watchdog Engine:** Added `/heartbeat` (and `PUT /image` alias) endpoint for active desktop clients (such as `tuneshine-windows`) to send periodic keep-alives.
- **Client Disconnect Protection:** Automatically clears the display (or reverts to active Spotify background playback) if a push client with active heartbeat stops communicating for `heartbeat_timeout` (default: 90 seconds), preventing displays from freezing on artwork when clients crash or shut down abruptly.
- **Configurable Watchdog Timeout:** Added `heartbeat_timeout` setting (default: 90.0s) to Hub configuration.

---

## [0.2.0] - 2026-08-29

### Added
- **Plex Media Server Webhook Integration:** Added `POST /webhook/plex` (and alias `POST /plex`) for instant, event-driven track display for Plexamp and Plex clients without polling.
- **Multi-Criteria Filtering:**
  - **Music-Only:** Automatically ignores movies, TV episodes, trailers, clips, and podcasts (`Metadata.type == "track"`).
  - **User Filtering:** `PLEX_ALLOWED_USERS` permits syncing only for specified Plex usernames/IDs (e.g. `david,admin`).
  - **Library Filtering:** `PLEX_ALLOWED_LIBRARIES` restricts syncing to specific music library section names or IDs (e.g. `Music,Lossless`).
  - **Player Filtering:** `PLEX_ALLOWED_PLAYERS` restricts syncing to dedicated clients (e.g. `Plexamp`).
- **Remote Artwork Fallback:** Downloads high-res artwork from PMS using `PLEX_URL` (or `PLEX_SERVER_URL`) and `PLEX_TOKEN` when artwork is not attached directly in the webhook request.
- **Unraid XML Template & Docker Compose Updates:** Added Plex configuration parameters to `tuneshine-hub.xml`, `docker-compose.yml`, and `.env.example`.

---

## [0.1.0] - 2026-08-28

### Added
- **Drop-in Hardware API:** Exposes `POST /image` and `DELETE /image` matching the physical Tuneshine device HTTP API.
- **Multi-Source Priority Arbitration:** Latest-event wins priority handling between Spotify background polling and external streaming clients (e.g. Navidrome, Windows Companion).
- **24/7 Spotify Polling Engine:** Background worker with token refresh, rate-limit backoff, and adaptive idle polling backoff.
- **Universal Image Processing:** Automatic conversion of JPEG/PNG/WebP images to 64×64 lossless WebP using Pillow.
- **Artwork Hash Deduplication:** Computes SHA-256 checksums to eliminate redundant display uploads.
- **Docker & Unraid Support:** Docker container packaging with healthcheck endpoints (`GET /health`, `GET /state`) and Unraid CA XML template.
