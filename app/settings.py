"""Application settings."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # TCP Server settings
    tcp_host: str = "0.0.0.0"
    tcp_port: int = 5221
    
    # Database settings
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/postgres"
    
    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    
    # Protocol settings
    frame_max_size: int = 4096
    read_timeout: float = 5.0
    idle_timeout: float = 900.0
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # CAN settings
    can_raw_enable: bool = True
    can_decode_enable: bool = True
    can_channels: list = [0]
    can_max_frame_rate: int = 2000
    can_tp_assemble_timeout_ms: int = 500
    
    # Dictionary paths
    can_dicts_j1939: str = "dicts/j1939.yaml"
    can_dicts_obd2: str = "dicts/obd2.yaml"
    can_dicts_brand_packs: list = ["dicts/volvo.yaml", "dicts/scania.yaml"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
