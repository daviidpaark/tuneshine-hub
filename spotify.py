import base64
import time
import logging
from typing import Optional, List
from dataclasses import dataclass
import httpx

logger = logging.getLogger("tuneshine-hub.spotify")


@dataclass
class SpotifyTrack:
    id: str
    name: str
    artist: str
    album: str
    image_url: str


class SpotifyClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.refresh_token = refresh_token.strip()

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._rate_limited_until: float = 0
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    @property
    def is_rate_limited(self) -> bool:
        return time.time() < self._rate_limited_until

    @property
    def rate_limit_remaining(self) -> float:
        return max(0.0, self._rate_limited_until - time.time())

    async def get_access_token(self) -> Optional[str]:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self.is_configured:
            return None

        if self.is_rate_limited:
            return None

        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_header = "Basic " + base64.b64encode(auth_str.encode()).decode()

        try:
            resp = await self._http.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            if resp.status_code == 429:
                self._handle_rate_limit(resp)
                return None

            if resp.status_code != 200:
                logger.warning(f"Spotify token refresh failed ({resp.status_code}): {resp.text}")
                return None

            data = resp.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)

            if not token:
                return None

            self._access_token = token
            # Cache with 60 second safety buffer
            self._token_expires_at = time.time() + max(0, expires_in - 60)
            return self._access_token

        except Exception as e:
            logger.error(f"Error requesting Spotify access token: {e}")
            return None

    def _handle_rate_limit(self, resp: httpx.Response):
        retry_after_str = resp.headers.get("Retry-After", "30")
        try:
            retry_after = max(1, int(retry_after_str))
        except ValueError:
            retry_after = 30
        self._rate_limited_until = time.time() + retry_after
        logger.warning(f"Rate limited by Spotify API (HTTP 429). Backing off for {retry_after}s.")

    async def get_currently_playing(self) -> Optional[SpotifyTrack]:
        if self.is_rate_limited:
            return None

        token = await self.get_access_token()
        if not token:
            return None

        try:
            resp = await self._http.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {token}"},
            )

            if resp.status_code == 401:
                # Token invalidated/expired
                self._access_token = None
                return None

            if resp.status_code == 429:
                self._handle_rate_limit(resp)
                return None

            if resp.status_code == 204 or resp.status_code < 200 or resp.status_code >= 300:
                return None

            data = resp.json()
            if not data.get("is_playing") or not data.get("item"):
                return None

            item = data["item"]
            track_id = item.get("id")
            track_name = item.get("name", "")

            artists = [a.get("name", "") for a in item.get("artists", []) if a.get("name")]
            artist_str = ", ".join(artists)

            album = item.get("album", {})
            album_name = album.get("name", "")
            images = album.get("images", [])

            # Choose optimal artwork (smallest or last is usually 64x64 or 300x300)
            image_url = ""
            if images:
                image_url = images[-1].get("url") or images[0].get("url")

            if not track_id or not image_url:
                return None

            return SpotifyTrack(
                id=track_id,
                name=track_name,
                artist=artist_str,
                album=album_name,
                image_url=image_url,
            )

        except Exception as e:
            logger.error(f"Error fetching Spotify currently playing: {e}")
            return None

    async def fetch_image(self, url: str) -> Optional[bytes]:
        try:
            resp = await self._http.get(url)
            if resp.status_code == 200:
                return resp.content
            return None
        except Exception as e:
            logger.error(f"Failed to download image from {url}: {e}")
            return None

    async def close(self):
        await self._http.aclose()
