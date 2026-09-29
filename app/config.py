from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Kubernetes AWS API"
    DATABASE_URL: str

    # Connection pool sizing, per pod. Total DB connections = pods * (size + overflow),
    # so these are tunable per environment rather than hardcoded in database.py
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    # Seconds to wait when opening a new DB connection. Keeps /readyz fast when the DB is
    # unreachable, instead of hanging until the OS gives up on the TCP connect.
    DB_CONNECT_TIMEOUT: int = 3

    LOG_LEVEL: str = "INFO"

    # This tells Pydantic to look for a file named .env to load these variables
    # extra="ignore": .env may hold values for other tools (e.g. TEST_DATABASE_URL for pytest)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Create a global instance of the settings to be used across the app
settings = Settings()
