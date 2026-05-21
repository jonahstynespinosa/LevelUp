from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/levelup"

    # Auth
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # App
    app_name: str = "LevelUp"
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()