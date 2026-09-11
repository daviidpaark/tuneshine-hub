# TuneShine Hub Instructions

## Repository Role & Architecture
- Central integration server and coordinator for TuneShine. Bridges Spotify, Plex, Windows desktop companion clients, and Navidrome to keep artwork and playback status synchronized with display devices.
- Built with Python 3.12+ and FastAPI / Uvicorn, with containerized deployment via Docker and Docker Compose.

## Development & Validation
- Use the virtual environment at `.venv\Scripts\python.exe` (or local Python 3.12+).
- Respect `requirements-lock.txt` and `requirements.txt`.
- Run unit tests:
  ```powershell
  & ".\.venv\Scripts\python.exe" -m unittest discover -s . -p "test_*.py" -v
  ```
- All automated tests should pass before concluding changes.

## Releases & CI
- Releases publish multi-arch Docker container images to GitHub Container Registry (`ghcr.io`) via `.github/workflows/docker-publish.yml`.
- Triggered by semantic version tags `v*` (e.g. `v0.2.0`).
- Always keep `CHANGELOG.md` synchronized before tagging.
- CI unit tests run on push and PR to `main` via `.github/workflows/ci.yml`.

## Git Workflow
- Do not commit or push unless explicitly requested by the user.
- Keep commits focused and scoped to this repository.

## Performance, Resource Lifecycle & Memory Hygiene
- **Explicit Handle & Stream Disposal:**
  - In `main.py`, FastAPI `UploadFile` handles must always be closed explicitly in `try ... finally` blocks (e.g. `await image.close()`) after processing image or payload data.
  - In `image_utils.py`, always close intermediate converted and resized Pillow `Image` objects.
- **Connection & Resource Pooling:**
  - Reuse persistent `httpx.AsyncClient` instances for outbound HTTP calls (Spotify API, Plex, device notifications) rather than instantiating per-request clients.
  - Ensure all HTTP clients are cleanly closed (`aclose()`) in FastAPI lifespan shutdown handlers.
- **Cache & Memory Bounding:**
  - Ensure in-memory playback history, thumbnail buffers, and active client sessions are bounded with max-size limits or TTL expiry to prevent memory growth during long-running 24/7 container operation.
