import json
import logging
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Response, status
from fastapi.responses import JSONResponse

from config import settings
from state_manager import HubStateManager
from spotify import SpotifyClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Silence verbose HTTP request logging from httpx/httpcore polling
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class EndpointFilter(logging.Filter):
    """Filter out health check requests from access logs to prevent log spam."""
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

logger = logging.getLogger("tuneshine-hub")

state_mgr = HubStateManager(settings.clean_tuneshine_host, clear_delay=settings.clear_delay)
spotify_client = SpotifyClient(
    client_id=settings.spotify_client_id,
    client_secret=settings.spotify_client_secret,
    refresh_token=settings.spotify_refresh_token,
)


async def spotify_polling_worker():
    """Background task that polls Spotify for currently playing tracks with adaptive idle backoff."""
    if not settings.spotify_enabled or not spotify_client.is_configured:
        logger.info("Spotify background polling is disabled or not configured")
        return

    logger.info(
        f"Spotify polling worker started (active: {settings.spotify_poll_interval}s, "
        f"idle: {settings.spotify_idle_poll_interval}s, idle delay: {settings.spotify_idle_delay}s)"
    )

    last_active_time = 0.0
    was_idle = True

    while True:
        sleep_duration = settings.spotify_poll_interval
        try:
            if spotify_client.is_rate_limited:
                cooldown = max(1.0, spotify_client.rate_limit_remaining)
                logger.info(f"Spotify rate-limit active, sleeping for {cooldown:.1f}s")
                await asyncio.sleep(cooldown)
                continue

            track = await spotify_client.get_currently_playing()
            now = time.time()

            if track:
                last_active_time = now
                if was_idle:
                    logger.info("Spotify playback detected, switched to active polling")
                    was_idle = False

                image_data = await spotify_client.fetch_image(track.image_url)
                if image_data:
                    metadata = {
                        "artistName": track.artist,
                        "albumName": track.album,
                        "serviceName": settings.spotify_servicename,
                        "itemId": track.id,
                    }
                    await state_mgr.on_spotify_playing(track.id, image_data, metadata)
            elif not spotify_client.is_rate_limited:
                await state_mgr.on_spotify_stopped()

            # Determine polling interval based on idle duration
            now = time.time()
            is_idle = (now - last_active_time) >= settings.spotify_idle_delay
            if is_idle and not was_idle:
                logger.info(
                    f"Spotify idle for {settings.spotify_idle_delay}s, switched to idle polling ({settings.spotify_idle_poll_interval}s)"
                )
                was_idle = True

            sleep_duration = settings.spotify_idle_poll_interval if is_idle else settings.spotify_poll_interval

        except Exception as e:
            logger.error(f"Error in Spotify polling loop: {e}")
            sleep_duration = settings.spotify_idle_poll_interval

        await asyncio.sleep(sleep_duration)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure healthcheck filter is attached to uvicorn access logger
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

    # Startup
    logger.info(f"Starting Tuneshine Hub (Target: {settings.clean_tuneshine_host or 'Not Configured'})")
    polling_task = asyncio.create_task(spotify_polling_worker())

    yield

    # Shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    await spotify_client.close()
    await state_mgr.close()
    logger.info("Tuneshine Hub shutdown complete")


app = FastAPI(
    title="Tuneshine Hub",
    description="Smart proxy and media hub controller for Tuneshine displays",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/image", summary="Upload artwork and metadata to display")
async def post_image(
    image: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
):
    """
    Standard Tuneshine drop-in endpoint.
    Accepts multipart form-data with 'image' and 'metadata'.
    """
    raw_image = await image.read()
    if not raw_image:
        return JSONResponse(status_code=400, content={"error": "Empty image payload"})

    parsed_meta = {}
    if metadata:
        try:
            parsed_meta = json.loads(metadata)
        except Exception:
            parsed_meta = {}

    await state_mgr.on_external_playing(raw_image, parsed_meta)
    return Response(status_code=status.HTTP_200_OK)


@app.delete("/image", summary="Clear display")
async def delete_image():
    """
    Standard Tuneshine drop-in endpoint.
    Clears the display (or reverts to active Spotify session if available).
    """
    await state_mgr.on_external_stopped()
    return Response(status_code=status.HTTP_200_OK)


@app.get("/health", summary="Health check")
async def health_check():
    return {
        "status": "ok",
        "tuneshine_host": settings.clean_tuneshine_host,
        "configured": state_mgr.is_configured,
    }


@app.get("/state", summary="Current playback state")
async def get_state():
    return {
        "active_source": state_mgr.active_source,
        "navidrome_playing": state_mgr.navidrome_state["is_playing"],
        "spotify_playing": state_mgr.spotify_state["is_playing"],
        "tuneshine_host": settings.clean_tuneshine_host,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)

