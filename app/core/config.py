from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_TIMEZONE: str = "UTC"
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_BUCKET: str

    class Config:
        env_file = ".env"

settings = Settings()
