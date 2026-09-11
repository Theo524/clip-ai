from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mock_mode: bool = True
    openai_api_key: str = ""
    openai_rank_model: str = "gpt-5"
    work_dir: str = "./work"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
