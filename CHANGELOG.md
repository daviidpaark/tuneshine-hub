# Changelog

All notable changes to the `tuneshine-hub` central service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.7] - 2026-09-30

### Fixed
- **Spotify Poll Errors:** A failed Spotify poll (timeout, 5xx, rejected token, or rate limit) was treated as playback stopping, so one API hiccup cleared the display and the next poll uploaded the artwork again. Poll errors now keep the current state, and the failure and recovery are logged once. Failures that last longer than 60 seconds (for example a revoked refresh token) are treated as Spotify stopping, so the display cannot freeze on the last track.
- **Shared Client Slot:** All external clients shared one playback slot, so a stop from one (for example Plexamp pausing on a phone) cleared the display while another (the Windows companion) was still playing. Each client now has its own slot, identified by an optional `?source=` query parameter on `POST`/`DELETE /image` and `/heartbeat` (Plex webhooks use their own slot). When the displayed client stops, the hub falls back to the most recent client still playing, then Spotify. Clients that send no `source` share the `default` slot as before. A held Spotify update or an undecodable cover no longer cancels the stopped client's pending clear, which could leave its artwork on the display.
- **Pinned Dependencies:** The Docker image and CI now install with `requirements-lock.txt` as constraints instead of unpinned `requirements.txt` ranges, so releases are reproducible.
- **Missing Settings:** `HEARTBEAT_TIMEOUT` (and `CLEAR_DELAY` in Compose) are now listed in `.env.example`, `docker-compose.yml`, and the Unraid template.

### Changed
- `GET /state` now also reports `active_client`, and `external_playing` is true when any client is playing.

---

## [0.2.6] - 2026-09-30

### Changed
- **Spotify Is the Fallback:** Spotify now shows only while no client source (Windows companion, Navidrome, Plex) is playing, instead of taking the display on every Spotify track change. Playing Spotify desktop on a PC with the Windows companion previously uploaded each song twice, once from the companion and once from the Spotify poller, because the two artwork sources never hash the same. Arbitration uses source priority only and never compares track, album, or artist names.

---

## [0.2.5] - 2026-09-30

### Added
- **Track Names:** Spotify pushes now include `trackName`, and client metadata is forwarded with it.
- **Metadata-Only Updates:** When consecutive tracks share artwork, the hub sends a JSON `POST /image` with only the new metadata instead of skipping the update, so the track name no longer goes stale. Older firmware that answers `409` falls back to a full upload.

### Fixed
- **Plex Track Name:** Plex metadata used `trackTitle`, which the device ignores; it now sends `trackName`.
- **Non-Square Artwork:** Artwork is center-cropped to a square before resizing instead of being stretched.
- **Client-Only Metadata:** Only device `TrackMetadata` fields are forwarded, so flags such as `heartbeat` no longer reach the device or trigger extra updates.

---

## [0.2.4] - 2026-09-28

### Fixed
- **Heartbeat Watchdog Clear:** The watchdog cancelled its own task while resolving a timeout, so the `DELETE /image` (or Spotify fallback push) was aborted and the Tuneshine kept showing stale artwork. `_cancel_heartbeat_watchdog()` now skips the current task.
- **Spotify Poll Display Takeover:** Repeat polls of the same Spotify track no longer take the display back from an external client or cancel its heartbeat watchdog. Artwork is only downloaded when the Spotify track changes.
- **Heartbeat While Spotify Active:** Heartbeats now refresh any playing external session, and a timeout marks it stopped even when Spotify holds the display, so Spotify stopping no longer falls back to stale artwork.
- **Plex Null Media Type:** Webhooks with `null` `type` or `librarySectionType` are ignored instead of returning HTTP 500.

---

## [0.2.3] - 2026-09-11

### Fixed
- **Upload File Handle Disposal:** Wrapped `image.read()` and `thumb.read()` in `try ... finally` blocks in `post_image` and `plex_webhook` endpoints to guarantee `await file.close()` is executed immediately, freeing temporary spool files and system handles.
- **Pillow Image Lifetime Management:** Explicitly close intermediate converted and resized Pillow `Image` objects in `image_utils.process_image_to_webp()` to prevent buffer retention.

---

## [0.2.2] - 2026-09-04

### Refactored
- **State Tracking Terminology:** Renamed internal state tracker variables and logs from `navidrome_state` to `external_state` across `state_manager.py` and `main.py` to clearly represent any external media source (Navidrome, Windows companion, Plex webhooks).

### Added
- **Exact Working Dependency Lock:** Added `requirements-lock.txt` for reproducible Hub deployment and container builds.

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
