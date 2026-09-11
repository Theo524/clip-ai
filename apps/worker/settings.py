from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mock_mode: bool = True
    openai_api_key: str = ""
    openai_rank_model: str = "gpt-5.6-luna"
    openai_transcribe_model: str = "whisper-1"
    work_dir: str = "./work"
    audio_chunk_seconds: int = 1200

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
