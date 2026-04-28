import json
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    CAPTCHA_SECRET_KEY: str
    CAPTCHA_VERIFY_URL: AnyHttpUrl

    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            # Caso CSV: "url1,url2"
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            # Caso JSON String: '["url1", "url2"]'
            # Pydantic v2 a veces parsea el JSON automáticamente, pero si llega como str:
            if isinstance(v, str) and v.startswith("["):
                return json.loads(v)
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
