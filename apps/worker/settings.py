from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mock_mode: bool = False

    # Development defaults: everything can run locally with no API credits.
    transcription_backend: str = "local"  # local | openai
    ranking_backend: str = "local"  # local | openai

    local_whisper_model: str = "tiny.en"
    local_whisper_device: str = "cpu"
    local_whisper_compute_type: str = "int8"

    openai_api_key: str = ""
    openai_rank_model: str = "gpt-5.6-luna"
    openai_transcribe_model: str = "whisper-1"

    work_dir: str = "./work"
    audio_chunk_seconds: int = 1200

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
