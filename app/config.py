from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_uri: str
    mongo_db_name: str = "urlshortener"
    upstash_redis_url: str
    base_url: str
    cache_ttl_seconds: int = 3600
    default_expiry_days: int = 30
    rate_limit: str = "10/minute"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
