from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mock_mode: bool = False

    # Development defaults: everything can run locally with no API credits.
    transcription_backend: str = "local"  # local | openai
    ranking_backend: str = "local"  # local | openai

    local_whisper_model: str = "tiny.en"
    local_whisper_refine_model: str = "base.en"
    local_whisper_device: str = "cpu"
    local_whisper_compute_type: str = "int8"
    local_whisper_cpu_threads: int = 4

    openai_api_key: str = ""
    openai_rank_model: str = "gpt-5.6-luna"
    openai_transcribe_model: str = "whisper-1"

    work_dir: str = "./work"
    audio_chunk_seconds: int = 1200
    cleanup_temp_audio: bool = True
    processing_profile: str = "balanced"  # low-memory | balanced | fast
    min_free_disk_gb: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
