from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    rabbitmq_url: str
    internal_token: str
    ingest_management_url: str = "http://ingest:8002"
    dashboard_token: str = "demo-dashboard-token"
    account_dashboard_tokens: str = "{}"
settings = Settings()
