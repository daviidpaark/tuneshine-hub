from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Tuneshine Device
    tuneshine_host: str = ""
    port: int = 8585

    # Debounce / Clearing / Watchdog Configuration
    clear_delay: float = 2.0
    heartbeat_timeout: float = 90.0

    # Spotify Configuration
    spotify_enabled: bool = False
    spotify_client_id: Optional[str] = ""
    spotify_client_secret: Optional[str] = ""
    spotify_refresh_token: Optional[str] = ""
    spotify_poll_interval: int = 5
    spotify_idle_poll_interval: int = 15
    spotify_idle_delay: float = 30.0
    spotify_servicename: str = "Spotify"

    # Plex Webhook Configuration
    plex_enabled: bool = True
    plex_allowed_users: Optional[str] = ""
    plex_allowed_libraries: Optional[str] = ""
    plex_allowed_players: Optional[str] = ""
    plex_url: Optional[str] = ""
    plex_server_url: Optional[str] = ""
    plex_token: Optional[str] = ""
    plex_servicename: str = "Plexamp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def clean_tuneshine_host(self) -> str:
        host = self.tuneshine_host.strip()
        host = host.removeprefix("http://").removeprefix("https://").rstrip("/")
        return host

    @property
    def resolved_plex_url(self) -> str:
        url = (self.plex_url or self.plex_server_url or "").strip().rstrip("/")
        return url


settings = Settings()
