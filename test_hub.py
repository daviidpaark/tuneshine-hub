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
        self.mgr = HubStateManager("192.168.1.100")
        self.mgr._push_to_tuneshine = AsyncMock()
        self.mgr._clear_tuneshine = AsyncMock()

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


if __name__ == "__main__":
    unittest.main()


