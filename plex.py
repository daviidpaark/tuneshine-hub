import json
import logging
from typing import Optional, Tuple, Dict, Any, List
import httpx

from config import Settings

logger = logging.getLogger("tuneshine-hub.plex")


class PlexWebhookHandler:
    """Handles validation, filtering, and artwork resolution for Plex Media Server Webhooks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.server_url = settings.resolved_plex_url
        self.token = (settings.plex_token or "").strip()
        self._http = httpx.AsyncClient(timeout=10.0)

    @staticmethod
    def parse_payload(raw_payload: str) -> Optional[dict]:
        """Parses the JSON string inside the multipart form-data 'payload' field."""
        if not raw_payload:
            return None
        try:
            return json.loads(raw_payload)
        except Exception as e:
            logger.warning(f"Failed to parse Plex webhook JSON payload: {e}")
            return None

    def _split_csv(self, val: Optional[str]) -> List[str]:
        if not val:
            return []
        return [x.strip().lower() for x in val.split(",") if x.strip()]

    def is_event_allowed(self, payload: dict) -> Tuple[bool, str]:
        """
        Validates whether a Plex webhook event should be processed.
        Returns (is_allowed, reason).
        """
        if not self.settings.plex_enabled:
            return False, "Plex webhook is disabled in hub settings"

        event = payload.get("event")
        if not event:
            return False, "Missing event field in payload"

        meta = payload.get("Metadata") or {}
        media_type = meta.get("type", "").lower()
        library_type = meta.get("librarySectionType", "").lower()

        # 1. Media Type Filter: Only process music tracks
        if media_type != "track" and library_type != "artist":
            return False, f"Ignored non-music media type: '{media_type or library_type}'"

        # 2. User Account Filter
        allowed_users = self._split_csv(self.settings.plex_allowed_users)
        if allowed_users:
            account = payload.get("Account") or {}
            user_title = str(account.get("title", "")).strip().lower()
            user_id = str(account.get("id", "")).strip().lower()

            if user_title not in allowed_users and user_id not in allowed_users:
                return False, f"User '{user_title or user_id}' not in allowed users list"

        # 3. Library Section Filter
        allowed_libraries = self._split_csv(self.settings.plex_allowed_libraries)
        if allowed_libraries:
            lib_title = str(meta.get("librarySectionTitle", "")).strip().lower()
            lib_id = str(meta.get("librarySectionID", "")).strip().lower()

            if lib_title not in allowed_libraries and lib_id not in allowed_libraries:
                return False, f"Library '{lib_title or lib_id}' not in allowed libraries list"

        # 4. Player Client Filter (e.g. Plexamp only)
        allowed_players = self._split_csv(self.settings.plex_allowed_players)
        if allowed_players:
            player = payload.get("Player") or {}
            player_title = str(player.get("title", "")).strip().lower()

            if player_title not in allowed_players:
                return False, f"Player '{player_title}' not in allowed players list"

        return True, "Allowed"

    def extract_track_metadata(self, payload: dict) -> Dict[str, Any]:
        """Extracts standard Tuneshine track metadata from Plex webhook payload."""
        meta = payload.get("Metadata") or {}
        player = payload.get("Player") or {}

        artist_name = meta.get("grandparentTitle") or meta.get("originalTitle") or ""
        album_name = meta.get("parentTitle") or ""
        track_title = meta.get("title") or ""
        item_id = str(meta.get("ratingKey") or meta.get("guid") or "")

        service_name = self.settings.plex_servicename or player.get("title") or "Plexamp"

        return {
            "artistName": artist_name,
            "albumName": album_name,
            "trackTitle": track_title,
            "serviceName": service_name,
            "itemId": item_id,
        }

    async def fetch_remote_artwork(self, thumb_path: str) -> Optional[bytes]:
        """Fetches artwork from Plex Media Server using configured server URL and token."""
        if not thumb_path or not self.server_url:
            return None

        clean_path = thumb_path if thumb_path.startswith("/") else f"/{thumb_path}"
        url = f"{self.server_url}{clean_path}"

        headers = {}
        if self.token:
            headers["X-Plex-Token"] = self.token

        try:
            resp = await self._http.get(url, headers=headers)
            if resp.status_code == 200 and resp.content:
                return resp.content
            logger.warning(f"Failed to fetch PMS artwork ({resp.status_code}): {url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading artwork from PMS ({url}): {e}")
            return None

    async def close(self):
        await self._http.aclose()
