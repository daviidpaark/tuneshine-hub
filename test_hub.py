import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import io
import time
import json
from PIL import Image
from fastapi.testclient import TestClient

from image_utils import process_image_to_webp, compute_image_hash
from state_manager import HubStateManager
from spotify import SpotifyClient
from main import app, state_mgr


class TestImageUtils(unittest.TestCase):
    def test_image_resizing_and_webp(self):
        # Create a test 100x100 RGB image
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        webp_bytes = process_image_to_webp(raw_bytes)
        self.assertIsNotNone(webp_bytes)

        # Verify output is a valid 64x64 WebP image
        out_img = Image.open(io.BytesIO(webp_bytes))
        self.assertEqual(out_img.size, (64, 64))
        self.assertEqual(out_img.format, "WEBP")

    def test_image_hash_consistency(self):
        data1 = b"test_image_data_123"
        data2 = b"test_image_data_123"
        data3 = b"different_data"
        self.assertEqual(compute_image_hash(data1), compute_image_hash(data2))
        self.assertNotEqual(compute_image_hash(data1), compute_image_hash(data3))


class TestStateManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mgr = HubStateManager("192.168.1.100", clear_delay=0.0)
        self.mgr._push_to_tuneshine = AsyncMock()
        self.mgr._clear_tuneshine = AsyncMock()

    async def asyncTearDown(self):
        await self.mgr.close()

    async def test_latest_event_arbitration(self):
        img = Image.new("RGB", (50, 50), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        dummy_img = buf.getvalue()
        meta1 = {"artistName": "Artist 1", "albumName": "Album 1", "serviceName": "Navidrome"}
        meta2 = {"artistName": "Artist 2", "albumName": "Album 2", "serviceName": "Spotify"}

        # 1. Navidrome starts playing
        await self.mgr.on_external_playing(dummy_img, meta1)
        self.assertEqual(self.mgr.active_source, "navidrome")
        self.assertTrue(self.mgr.navidrome_state["is_playing"])

        # 2. Spotify starts playing -> Latest event wins
        await self.mgr.on_spotify_playing("spot1", dummy_img, meta2)
        self.assertEqual(self.mgr.active_source, "spotify")
        self.assertTrue(self.mgr.spotify_state["is_playing"])

        # 3. Spotify stops -> Automatically reverts to active Navidrome
        await self.mgr.on_spotify_stopped()
        self.assertEqual(self.mgr.active_source, "navidrome")
        self.assertTrue(self.mgr.navidrome_state["is_playing"])

        # 4. Navidrome stops -> Display clears to idle
        await self.mgr.on_external_stopped()
        self.assertIsNone(self.mgr.active_source)
        self.assertFalse(self.mgr.navidrome_state["is_playing"])
        self.mgr._clear_tuneshine.assert_called()

    async def test_debounced_clear_cancellation(self):
        # Test that rapid DELETE -> POST cancels the pending clear and avoids blank screen
        mgr = HubStateManager("192.168.1.100", clear_delay=0.1)
        mgr._push_to_tuneshine = AsyncMock()
        mgr._clear_tuneshine = AsyncMock()

        img = Image.new("RGB", (50, 50), color=(0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        dummy_img = buf.getvalue()
        meta1 = {"artistName": "Artist 1", "albumName": "Album 1", "serviceName": "Navidrome"}
        meta2 = {"artistName": "Artist 2", "albumName": "Album 2", "serviceName": "Navidrome"}

        # 1. Initial track playing
        await mgr.on_external_playing(dummy_img, meta1)
        self.assertEqual(mgr.active_source, "navidrome")

        # 2. External stopped event arrives (e.g. Navidrome websocket disconnect or track change)
        await mgr.on_external_stopped()
        self.assertIsNotNone(mgr._pending_clear_task)

        # 3. Next track arrives immediately (within debounce window)
        await asyncio.sleep(0.02)
        await mgr.on_external_playing(dummy_img, meta2)

        # 4. Wait out the original debounce period
        await asyncio.sleep(0.15)

        # Clear should NEVER have been called on the physical device
        mgr._clear_tuneshine.assert_not_called()
        self.assertEqual(mgr.active_source, "navidrome")
        await mgr.close()

    async def test_debounced_clear_execution(self):
        # Test that clear executes after debounce duration when no new track arrives
        mgr = HubStateManager("192.168.1.100", clear_delay=0.05)
        mgr._push_to_tuneshine = AsyncMock()
        mgr._clear_tuneshine = AsyncMock()

        img = Image.new("RGB", (50, 50), color=(0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        dummy_img = buf.getvalue()
        meta = {"artistName": "Artist 1", "albumName": "Album 1", "serviceName": "Navidrome"}

        await mgr.on_external_playing(dummy_img, meta)
        await mgr.on_external_stopped()

        # Before delay completes, display has not cleared
        self.assertFalse(mgr.navidrome_state["is_playing"])
        mgr._clear_tuneshine.assert_not_called()

        # After delay completes, clear is executed
        await asyncio.sleep(0.08)
        mgr._clear_tuneshine.assert_called_once()
        self.assertIsNone(mgr.active_source)
        await mgr.close()


class TestSpotifyClient(unittest.IsolatedAsyncioTestCase):
    async def test_spotify_rate_limit_backoff(self):
        client = SpotifyClient("id", "secret", "token")
        client._access_token = "valid_token"
        client._token_expires_at = time.time() + 3600

        # Simulate 429 response with Retry-After header
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "15"}

        with patch.object(client._http, "get", return_value=mock_response):
            track = await client.get_currently_playing()
            self.assertIsNone(track)
            self.assertTrue(client.is_rate_limited)
            self.assertGreater(client.rate_limit_remaining, 10.0)

        # Subsequent call should return None immediately without network request
        with patch.object(client._http, "get") as mock_get:
            track = await client.get_currently_playing()
            self.assertIsNone(track)
            mock_get.assert_not_called()


class TestFastAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        state_mgr._push_to_tuneshine = AsyncMock()
        state_mgr._clear_tuneshine = AsyncMock()

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_state_endpoint(self):
        resp = self.client.get("/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("active_source", data)
        self.assertIn("navidrome_playing", data)
        self.assertIn("spotify_playing", data)

    def test_post_image_and_delete_endpoints(self):
        img = Image.new("RGB", (50, 50), color=(255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_jpeg = buf.getvalue()

        meta = {"artistName": "Test Artist", "albumName": "Test Album", "serviceName": "Navidrome"}

        # POST /image
        resp = self.client.post(
            "/image",
            files={"image": ("cover.jpg", raw_jpeg, "image/jpeg")},
            data={"metadata": json.dumps(meta)},
        )
        self.assertEqual(resp.status_code, 200)

        # Verify state
        state_resp = self.client.get("/state")
        self.assertEqual(state_resp.json()["active_source"], "navidrome")

        # DELETE /image
        del_resp = self.client.delete("/image")
        self.assertEqual(del_resp.status_code, 200)


class TestPlexWebhook(unittest.TestCase):
    def setUp(self):
        state_mgr._push_to_tuneshine = AsyncMock()
        state_mgr._clear_tuneshine = AsyncMock()
        self.client = TestClient(app)

    def _create_sample_image(self) -> bytes:
        img = Image.new("RGB", (64, 64), color=(0, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_plex_webhook_play_with_attached_thumb(self):
        raw_img = self._create_sample_image()
        payload = {
            "event": "media.play",
            "Account": {"title": "david", "id": 1},
            "Player": {"title": "Plexamp"},
            "Metadata": {
                "type": "track",
                "librarySectionTitle": "Music",
                "librarySectionID": 2,
                "title": "Track Title",
                "parentTitle": "Album Title",
                "grandparentTitle": "Artist Name",
                "ratingKey": "9999",
            },
        }

        resp = self.client.post(
            "/webhook/plex",
            data={"payload": json.dumps(payload)},
            files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "playing")
        self.assertEqual(data["metadata"]["artistName"], "Artist Name")
        self.assertEqual(data["metadata"]["albumName"], "Album Title")
        self.assertEqual(data["metadata"]["trackTitle"], "Track Title")
        self.assertEqual(data["metadata"]["serviceName"], "Plexamp")

    def test_plex_webhook_stop(self):
        payload = {
            "event": "media.stop",
            "Account": {"title": "david"},
            "Player": {"title": "Plexamp"},
            "Metadata": {
                "type": "track",
                "title": "Track Title",
            },
        }

        resp = self.client.post(
            "/webhook/plex",
            data={"payload": json.dumps(payload)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "stopped")

    def test_plex_webhook_filters_non_music(self):
        raw_img = self._create_sample_image()
        # Episode/Movie payload
        payload = {
            "event": "media.play",
            "Account": {"title": "david"},
            "Player": {"title": "Plex for Apple TV"},
            "Metadata": {
                "type": "episode",
                "title": "Episode 1",
                "parentTitle": "Season 1",
                "grandparentTitle": "Show Name",
            },
        }

        resp = self.client.post(
            "/webhook/plex",
            data={"payload": json.dumps(payload)},
            files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.assertIn("non-music", resp.json()["reason"])

    def test_plex_webhook_user_filter(self):
        from config import settings
        orig_users = settings.plex_allowed_users
        try:
            settings.plex_allowed_users = "david,admin"
            raw_img = self._create_sample_image()

            # Allowed user
            payload_ok = {
                "event": "media.play",
                "Account": {"title": "david"},
                "Metadata": {"type": "track", "title": "Song"},
            }
            resp_ok = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_ok)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_ok.json()["status"], "playing")

            # Disallowed user
            payload_bad = {
                "event": "media.play",
                "Account": {"title": "guest_user"},
                "Metadata": {"type": "track", "title": "Song"},
            }
            resp_bad = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_bad)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_bad.json()["status"], "ignored")
            self.assertIn("not in allowed users", resp_bad.json()["reason"])
        finally:
            settings.plex_allowed_users = orig_users

    def test_plex_webhook_library_filter(self):
        from config import settings
        orig_libs = settings.plex_allowed_libraries
        try:
            settings.plex_allowed_libraries = "Music,Lossless,4"
            raw_img = self._create_sample_image()

            # Allowed library title
            payload_ok = {
                "event": "media.play",
                "Account": {"title": "david"},
                "Metadata": {"type": "track", "librarySectionTitle": "Music", "title": "Song"},
            }
            resp_ok = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_ok)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_ok.json()["status"], "playing")

            # Allowed library ID
            payload_id_ok = {
                "event": "media.play",
                "Account": {"title": "david"},
                "Metadata": {"type": "track", "librarySectionID": 4, "title": "Song"},
            }
            resp_id_ok = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_id_ok)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_id_ok.json()["status"], "playing")

            # Disallowed library
            payload_bad = {
                "event": "media.play",
                "Account": {"title": "david"},
                "Metadata": {"type": "track", "librarySectionTitle": "Audiobooks", "librarySectionID": 9, "title": "Song"},
            }
            resp_bad = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_bad)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_bad.json()["status"], "ignored")
            self.assertIn("not in allowed libraries", resp_bad.json()["reason"])
        finally:
            settings.plex_allowed_libraries = orig_libs

    def test_plex_webhook_player_filter(self):
        from config import settings
        orig_players = settings.plex_allowed_players
        try:
            settings.plex_allowed_players = "Plexamp"
            raw_img = self._create_sample_image()

            # Allowed player
            payload_ok = {
                "event": "media.play",
                "Player": {"title": "Plexamp"},
                "Metadata": {"type": "track", "title": "Song"},
            }
            resp_ok = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_ok)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_ok.json()["status"], "playing")

            # Disallowed player
            payload_bad = {
                "event": "media.play",
                "Player": {"title": "Plex Web"},
                "Metadata": {"type": "track", "title": "Song"},
            }
            resp_bad = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload_bad)},
                files={"thumb": ("thumb.jpg", raw_img, "image/jpeg")},
            )
            self.assertEqual(resp_bad.json()["status"], "ignored")
            self.assertIn("not in allowed players", resp_bad.json()["reason"])
        finally:
            settings.plex_allowed_players = orig_players

    def test_plex_webhook_remote_artwork_fetch(self):
        from main import plex_handler
        raw_img = self._create_sample_image()

        with patch.object(plex_handler, "fetch_remote_artwork", new=AsyncMock(return_value=raw_img)):
            payload = {
                "event": "media.play",
                "Metadata": {
                    "type": "track",
                    "title": "Remote Song",
                    "parentTitle": "Remote Album",
                    "grandparentTitle": "Remote Artist",
                    "thumb": "/library/metadata/12345/thumb/12345",
                },
            }

            resp = self.client.post(
                "/webhook/plex",
                data={"payload": json.dumps(payload)},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "playing")
            self.assertEqual(resp.json()["metadata"]["artistName"], "Remote Artist")


if __name__ == "__main__":
    unittest.main()


