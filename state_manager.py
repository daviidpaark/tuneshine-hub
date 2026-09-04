import json
import logging
import asyncio
from typing import Optional, Dict, Any
import httpx
from image_utils import process_image_to_webp, compute_image_hash

logger = logging.getLogger("tuneshine-hub.state")


class HubStateManager:
    def __init__(self, tuneshine_host: str, clear_delay: float = 2.0, heartbeat_timeout: float = 90.0):
        self.tuneshine_host = tuneshine_host.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
        self._http = httpx.AsyncClient(timeout=15.0)
        self._lock = asyncio.Lock()
        self.clear_delay = clear_delay
        self.heartbeat_timeout = heartbeat_timeout

        self.active_source: Optional[str] = None  # "external", "spotify", or None
        self.last_uploaded_hash: Optional[str] = None
        self._pending_clear_task: Optional[asyncio.Task] = None
        self._heartbeat_watchdog_task: Optional[asyncio.Task] = None

        self.external_state: Dict[str, Any] = {
            "is_playing": False,
            "track_id": None,
            "webp_data": None,
            "metadata": None,
        }

        self.spotify_state: Dict[str, Any] = {
            "is_playing": False,
            "track_id": None,
            "webp_data": None,
            "metadata": None,
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.tuneshine_host)

    def _cancel_pending_clear(self):
        if self._pending_clear_task and not self._pending_clear_task.done():
            self._pending_clear_task.cancel()
            self._pending_clear_task = None

    def _cancel_heartbeat_watchdog(self):
        if self._heartbeat_watchdog_task and not self._heartbeat_watchdog_task.done():
            self._heartbeat_watchdog_task.cancel()
            self._heartbeat_watchdog_task = None

    def _arm_heartbeat_watchdog(self):
        self._cancel_heartbeat_watchdog()
        if self.heartbeat_timeout > 0:
            self._heartbeat_watchdog_task = asyncio.create_task(self._delayed_heartbeat_timeout())

    async def _delayed_heartbeat_timeout(self):
        try:
            await asyncio.sleep(self.heartbeat_timeout)
            async with self._lock:
                if self.external_state["is_playing"] and self.active_source == "external":
                    logger.warning(
                        f"External client heartbeat timed out ({self.heartbeat_timeout}s without update); clearing display"
                    )
                    self.external_state["is_playing"] = False
                    await self._resolve_external_stop()
        except asyncio.CancelledError:
            pass

    async def on_heartbeat(self, source: str = "windows") -> bool:
        """Called when a periodic heartbeat ping is received from an active client."""
        async with self._lock:
            if self.active_source == "external" and self.external_state["is_playing"]:
                self._arm_heartbeat_watchdog()
                logger.debug(f"Heartbeat received from '{source}', watchdog timer reset")
                return True
            return False

    async def on_external_playing(self, raw_image_data: bytes, metadata: Dict[str, Any]):
        """Called when Navidrome (or another external client) starts playing a track."""
        async with self._lock:
            self._cancel_pending_clear()
            if metadata.get("heartbeat"):
                self._arm_heartbeat_watchdog()
            else:
                self._cancel_heartbeat_watchdog()
            try:
                webp_data = process_image_to_webp(raw_image_data)
            except Exception as e:
                logger.error(f"Failed to convert external image to WebP: {e}")
                return

            item_id = metadata.get("itemId") or metadata.get("artistName", "") + metadata.get("albumName", "")

            self.external_state = {
                "is_playing": True,
                "track_id": item_id,
                "webp_data": webp_data,
                "metadata": metadata,
            }

            # Latest-event wins: external client takes the display
            self.active_source = "external"
            await self._push_to_tuneshine(webp_data, metadata)

    async def on_external_stopped(self):
        """Called when Navidrome pauses or stops playback."""
        async with self._lock:
            self._cancel_heartbeat_watchdog()
            self.external_state["is_playing"] = False

            if self.active_source == "external":
                self._cancel_pending_clear()
                if self.clear_delay > 0:
                    self._pending_clear_task = asyncio.create_task(self._delayed_external_stop())
                else:
                    await self._resolve_external_stop()

    async def _delayed_external_stop(self):
        try:
            await asyncio.sleep(self.clear_delay)
            async with self._lock:
                await self._resolve_external_stop()
        except asyncio.CancelledError:
            pass

    async def _resolve_external_stop(self):
        self._cancel_heartbeat_watchdog()
        if self.external_state["is_playing"] or self.active_source != "external":
            return

        # Fallback: if Spotify is currently playing, switch back to Spotify
        if self.spotify_state["is_playing"] and self.spotify_state["webp_data"]:
            logger.info("External playback stopped, reverting to active Spotify session")
            self.active_source = "spotify"
            await self._push_to_tuneshine(
                self.spotify_state["webp_data"],
                self.spotify_state["metadata"],
                force=True,
            )
        else:
            self.active_source = None
            await self._clear_tuneshine()

    async def on_spotify_playing(self, track_id: str, raw_image_data: bytes, metadata: Dict[str, Any]):
        """Called when Spotify playback is active with a track."""
        async with self._lock:
            self._cancel_pending_clear()
            self._cancel_heartbeat_watchdog()
            # Check if same Spotify track
            if self.spotify_state["is_playing"] and self.spotify_state["track_id"] == track_id and self.active_source == "spotify":
                return

            try:
               webp_data = process_image_to_webp(raw_image_data)
            except Exception as e:
                logger.error(f"Failed to convert Spotify artwork to WebP: {e}")
                return

            self.spotify_state = {
                "is_playing": True,
                "track_id": track_id,
                "webp_data": webp_data,
                "metadata": metadata,
            }

            # Latest-event wins: Spotify event updates display
            self.active_source = "spotify"
            await self._push_to_tuneshine(webp_data, metadata)

    async def on_spotify_stopped(self):
        """Called when Spotify playback is paused or stopped."""
        async with self._lock:
            if not self.spotify_state["is_playing"]:
                return

            self.spotify_state["is_playing"] = False

            if self.active_source == "spotify":
                self._cancel_pending_clear()
                if self.clear_delay > 0:
                    self._pending_clear_task = asyncio.create_task(self._delayed_spotify_stop())
                else:
                    await self._resolve_spotify_stop()

    async def _delayed_spotify_stop(self):
        try:
            await asyncio.sleep(self.clear_delay)
            async with self._lock:
                await self._resolve_spotify_stop()
        except asyncio.CancelledError:
            pass

    async def _resolve_spotify_stop(self):
        if self.spotify_state["is_playing"] or self.active_source != "spotify":
            return

        # Fallback: if external client is currently playing, switch back
        if self.external_state["is_playing"] and self.external_state["webp_data"]:
            logger.info("Spotify stopped, reverting to active external playback")
            self.active_source = "external"
            await self._push_to_tuneshine(
                self.external_state["webp_data"],
                self.external_state["metadata"],
                force=True,
            )
        else:
            self.active_source = None
            await self._clear_tuneshine()

    async def _push_to_tuneshine(self, webp_data: bytes, metadata: Dict[str, Any], force: bool = False):
        if not self.is_configured:
            logger.warning("TUNESHINE_HOST not set; skipping upload")
            return

        img_hash = compute_image_hash(webp_data)
        if not force and self.last_uploaded_hash == img_hash:
            return

        url = f"http://{self.tuneshine_host}/image"
        files = {
            "image": ("cover.webp", webp_data, "image/webp"),
            "metadata": (None, json.dumps(metadata), "application/json"),
        }

        try:
            resp = await self._http.post(url, files=files)
            if 200 <= resp.status_code < 300:
                self.last_uploaded_hash = img_hash
                logger.info(f"Pushed to Tuneshine [{metadata.get('serviceName', 'Media')}]: {metadata.get('artistName')} - {metadata.get('albumName')}")
            else:
                logger.warning(f"POST /image to Tuneshine returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error posting image to Tuneshine ({url}): {e}")

    async def _clear_tuneshine(self):
        if not self.is_configured:
            return

        url = f"http://{self.tuneshine_host}/image"
        try:
            resp = await self._http.delete(url)
            if 200 <= resp.status_code < 300:
                self.last_uploaded_hash = None
                logger.info("Cleared Tuneshine display")
            else:
                logger.warning(f"DELETE /image returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error sending DELETE to Tuneshine ({url}): {e}")

    async def close(self):
        self._cancel_pending_clear()
        self._cancel_heartbeat_watchdog()
        await self._http.aclose()
