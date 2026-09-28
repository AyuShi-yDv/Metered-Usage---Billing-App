from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    rabbitmq_url: str
    internal_token: str
    max_body_bytes: int = 16_384
settings = Settings()
