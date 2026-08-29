# Tuneshine Hub

[![CI](https://github.com/daviidpaark/tuneshine-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/daviidpaark/tuneshine-hub/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/daviidpaark/tuneshine-hub/pkgs/container/tuneshine-hub)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A smart proxy controller and media aggregator for [Tuneshine](https://www.tuneshine.rocks/) LED displays.

Acts as a central hub on your local network: it automatically manages **Spotify** background playback polling, receives live playback from **Navidrome** (via the [Navidrome Tuneshine Plugin](https://github.com/daviidpaark/tuneshine-navidrome)), **Windows** (via [Tuneshine Windows](https://github.com/daviidpaark/tuneshine-windows)), and **Plex / Plexamp** (via native webhooks), handles automatic **Latest-Event-Wins** priority arbitration, and forwards 64×64 lossless WebP artwork to your physical Tuneshine device.

---

## The Tuneshine Ecosystem

- **[tuneshine-hub](https://github.com/daviidpaark/tuneshine-hub)** *(This repository)*: Central Docker hub service. Manages 24/7 background Spotify tracking, converts raw artwork to 64×64 WebP, arbitrates multi-source priority, and drives your physical Tuneshine device.
- **[tuneshine-windows](https://github.com/daviidpaark/tuneshine-windows)**: Standalone Windows System Tray desktop companion. Hooks into Windows Media Controls (SMTC) to capture and stream real-time playback from Spotify, Apple Music, YouTube, Tidal, and local players to Tuneshine Hub (or directly to a physical Tuneshine device).
- **[tuneshine-navidrome](https://github.com/daviidpaark/tuneshine-navidrome)**: Official Navidrome plugin. Streams live playback and cover art from your Navidrome music server to Tuneshine Hub (or directly to a physical Tuneshine device).

---

## Features

- **Drop-in Hardware API:** Exposes `POST /image` and `DELETE /image` matching the real Tuneshine hardware HTTP API.
- **Latest-Event-Wins Priority Arbitration:**
  - Whichever music service (Navidrome, Plexamp, Windows Companion, or Spotify) starts or changes tracks most recently claims the display.
  - When one service pauses or stops, the hub seamlessly falls back to the other active music stream before clearing to idle.
- **Standalone 24/7 Spotify Engine:** Polls Spotify Web API asynchronously in the background with automatic token refreshing, rate-limit backoff, and CDN image downscaling.
- **Plex & Plexamp Webhook Support:** Instant, event-driven track display via Plex Media Server webhooks with multi-criteria user, library, and player filtering.
- **Universal Image Processing:** Automatically converts incoming JPEG/PNG/WebP images to 64×64 lossless WebP using Pillow.
- **Artwork Hash Deduplication:** Eliminates redundant uploads for consecutive tracks with identical album artwork.

---

## Architecture

```text
  ┌──────────────────────┐      ┌─────────────────────────┐
  │   Spotify Web API    │      │  Plex Media Server /    │
  │   (Background Poll)  │      │  Plexamp Webhook Event  │
  └──────────┬───────────┘      └────────────┬────────────┘
             │                               │ POST /webhook/plex
             ▼                               ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                   tuneshine-hub (Docker)                    │
 │  - Latest-event wins arbitration                            │  Upload 64x64 WebP  ┌─────────────────┐
 │  - Spotify token management & rate limit backoff            │ ──────────────────► │ Tuneshine (LAN) │
 │  - Image downscaling to 64x64 WebP (Pillow)                 │                     └─────────────────┘
 │  - Drop-in API (POST /image, DELETE /image)                 │
 └──────────────────────▲──────────────────────▲───────────────┘
                        │                      │ POST /image (Standard API)
         ┌──────────────┴──────────────┐       │
         │     tuneshine-navidrome     │       │ ┌─────────────────────────┐
         │           Plugin            │       └─┤    tuneshine-windows    │
         └─────────────────────────────┘         │    Desktop Companion    │
                                                 └─────────────────────────┘
```

---

## Quick Start

### Option A: Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
services:
  tuneshine-hub:
    image: ghcr.io/daviidpaark/tuneshine-hub:latest
    container_name: tuneshine-hub
    restart: unless-stopped
    ports:
      - "8585:8585"
    environment:
      # IP or hostname of your physical Tuneshine device
      - TUNESHINE_HOST=192.168.1.100
      - PORT=8585

      # Optional Spotify configuration:
      # - SPOTIFY_ENABLED=true
      # - SPOTIFY_CLIENT_ID=your_spotify_client_id
      # - SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
      # - SPOTIFY_REFRESH_TOKEN=your_spotify_refresh_token
```

Start the service:

```sh
docker compose up -d
```

### Option B: Docker CLI (One-Liner)

Run directly with `docker run`:

```sh
docker run -d \
  --name tuneshine-hub \
  --restart unless-stopped \
  -p 8585:8585 \
  -e TUNESHINE_HOST=192.168.1.100 \
  ghcr.io/daviidpaark/tuneshine-hub:latest
```

### Option C: Unraid (Community Applications)

Tuneshine Hub includes an Unraid Community Applications XML template ([`tuneshine-hub.xml`](tuneshine-hub.xml)):

1. In the Unraid WebGUI, navigate to **Docker** -> **Add Container**.
2. Point the template repository/URL to:
   ```
   https://raw.githubusercontent.com/daviidpaark/tuneshine-hub/main/tuneshine-hub.xml
   ```
3. Set your `TUNESHINE_HOST` (and optional Spotify / Plex parameters), then click **Apply**.

---

## Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `TUNESHINE_HOST` | **Yes** | — | IP or hostname of your physical Tuneshine device (e.g. `192.168.1.100` or `tuneshine.local`) |
| `PORT` | No | `8585` | Port for the Hub HTTP server |
| `CLEAR_DELAY` | No | `2.0` | Debounce delay in seconds before clearing display or switching sources (prevents screen flicker during seeks & track transitions) |
| `SPOTIFY_ENABLED` | No | `false` | Enable Spotify Web API polling |
| `SPOTIFY_CLIENT_ID` | Conditional | — | Spotify Developer Client ID (required if Spotify is enabled) |
| `SPOTIFY_CLIENT_SECRET` | Conditional | — | Spotify Developer Client Secret (required if Spotify is enabled) |
| `SPOTIFY_REFRESH_TOKEN` | Conditional | — | Spotify OAuth Refresh Token (required if Spotify is enabled) |
| `SPOTIFY_POLL_INTERVAL` | No | `5` | Spotify active polling interval in seconds when music is playing (default: 5) |
| `SPOTIFY_IDLE_POLL_INTERVAL` | No | `15` | Spotify idle polling interval in seconds when nothing is playing (default: 15) |
| `SPOTIFY_IDLE_DELAY` | No | `30.0` | Inactivity delay in seconds before switching to idle polling rate (default: 30.0) |
| `SPOTIFY_SERVICENAME` | No | `Spotify` | Label displayed on Tuneshine for Spotify tracks |
| `PLEX_ENABLED` | No | `true` | Enable Plex Webhook endpoint (`/webhook/plex`) |
| `PLEX_ALLOWED_USERS` | No | — | Comma-separated list of allowed Plex usernames or IDs (e.g. `david,admin`). Empty allows all users |
| `PLEX_ALLOWED_LIBRARIES` | No | — | Comma-separated list of allowed music library names or IDs (e.g. `Music,Lossless`). Empty allows all music libraries |
| `PLEX_ALLOWED_PLAYERS` | No | — | Comma-separated list of allowed player clients (e.g. `Plexamp`). Empty allows any Plex player |
| `PLEX_SERVER_URL` | No | — | Base URL of Plex Media Server (e.g. `http://192.168.1.50:32400`) to fetch remote cover art if not attached in webhook |
| `PLEX_TOKEN` | No | — | Plex authentication token (`X-Plex-Token`) for downloading high-res artwork from PMS |
| `PLEX_SERVICENAME` | No | `Plexamp` | Label displayed on Tuneshine for Plexamp tracks |

---

## Plex / Plexamp Webhook Integration

Tuneshine Hub includes native support for **Plex Media Server Webhooks** (Plex Pass feature). Whenever Plexamp (or any Plex client) plays music, PMS pushes immediate event-driven metadata and artwork without any polling.

### Setup Instructions:
1. In Plex Web, go to **Settings** -> **Webhooks**.
2. Click **Add Webhook** and enter:
   ```
   http://<hub-ip>:8585/webhook/plex
   ```
3. Save the webhook.

### Filtering Options:
* **Music-Only Filtering:** Non-music media (movies, TV shows, videos, clips) is automatically ignored.
* **User Filtering:** Set `PLEX_ALLOWED_USERS="david"` so playback from other family members or shared users is ignored.
* **Library Filtering:** Set `PLEX_ALLOWED_LIBRARIES="Music"` to only display tracks from specific music libraries.
* **Player Filtering:** Set `PLEX_ALLOWED_PLAYERS="Plexamp"` to only sync playback from dedicated Plexamp clients.

---

## Connecting Clients (Navidrome, Windows & Others)

### Navidrome Plugin
In the [Navidrome Tuneshine Plugin](https://github.com/daviidpaark/tuneshine-navidrome):
1. Set **Operation Mode** to `Tuneshine Hub (Offload Processing)`.
2. Set **Target Host** to your Hub instance address (e.g. `tuneshine-hub:8585` or `<hub-ip>:8585`).
3. Save settings.

### Windows Desktop Companion
In [Tuneshine Windows](https://github.com/daviidpaark/tuneshine-windows):
1. Open the **Dashboard** (double-click the system tray icon).
2. Set **Operation Mode** to `Tuneshine Hub (Offload)`.
3. Enter your **Target Host** (e.g. `http://<hub-ip>:8585`).
4. Ensure **Sync Enabled** is toggled on.

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/image` | Multipart artwork upload (`image` & `metadata`). Drop-in replacement for hardware API. |
| `DELETE` | `/image` | Clears display or reverts to active Spotify playback. |
| `POST` | `/webhook/plex` | Plex Media Server webhook listener (also aliased at `/plex`). |
| `GET` | `/health` | Health check endpoint returning device connection status. |
| `GET` | `/state` | Returns active playback source and playback status. |
| `GET` | `/docs` | Interactive Swagger / OpenAPI documentation UI. |

---

## Development & Building from Source

To contribute, develop, or build from source:

1. Clone the repository:
   ```sh
   git clone https://github.com/daviidpaark/tuneshine-hub.git
   cd tuneshine-hub
   ```

2. Set up a Python environment and install dependencies:
   ```sh
   python -m venv .venv
   source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Run unit tests locally:
   ```sh
   python -m unittest discover -s . -p "test_*.py" -v
   ```

4. Build the local Docker image:
   ```sh
   docker build -t tuneshine-hub .
   ```

---

## AI Disclosure & Personal Project Note

> [!NOTE]
> This project was developed as a personal home lab tool with the assistance of **Google Antigravity (Gemini Flash)** AI pair programming. It is shared publicly for the benefit of the community and other Tuneshine owners. Contributions, feedback, and issue reports are always welcome!

---

## License

MIT License. See [LICENSE](LICENSE) for details.
