from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/observer.db"
    data_dir: Path = Path("data")
    app_api_key: SecretStr = SecretStr("")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    polling_enabled: bool = True
    center_lat: float = Field(30.0878597, ge=-90, le=90)
    center_lon: float = Field(31.3413867, ge=-180, le=180)
    radius_m: int = Field(5000, ge=1000, le=5000)
    tomtom_api_key: SecretStr = SecretStr("")
    aisstream_api_key: SecretStr = SecretStr("")
    openaq_api_key: SecretStr = SecretStr("")
    asf_bearer_token: SecretStr = SecretStr("")
    copernicus_access_token: SecretStr = SecretStr("")
    camera_allowed_hosts: str = "test-streams.mux.dev"
    yolox_model_path: str = ""
    camera_processing_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_username: str = ""
    mqtt_password: SecretStr = SecretStr("")
    mqtt_topic: str = "nile/observations"
    serial_port: str = ""
    serial_baud: int = 115200
    source_plugins: str = ""
    max_download_bytes: int = 2_000_000_000


@lru_cache
def get_settings():
    # Preserve explicitly injected environment values, including credential references.
    load_dotenv(".env", override=False)
    return Settings()
