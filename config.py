from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Tuneshine Device
    tuneshine_host: str = ""
    port: int = 8585

    # Spotify Configuration
    spotify_enabled: bool = False
    spotify_client_id: Optional[str] = ""
    spotify_client_secret: Optional[str] = ""
    spotify_refresh_token: Optional[str] = ""
    spotify_poll_interval: int = 3
    spotify_servicename: str = "Spotify"

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


settings = Settings()
