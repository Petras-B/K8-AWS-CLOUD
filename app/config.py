from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Kubernetes AWS API"
    DATABASE_URL: str
    
    # This tells Pydantic to look for a file named .env to load these variables
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Create a global instance of the settings to be used across the app
settings = Settings()