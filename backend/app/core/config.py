from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Contract Review System"
    DATABASE_URL: str
    OLLAMA_URL: str = "http://51.112.105.60:11434"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    
    # Clause extraction settings
    ENABLE_CLAUSE_VALIDATION: bool = True
    VALIDATION_BATCH_SIZE: int = 10
    MIN_CLAUSE_QUALITY: float = 0.5
    INCLUDE_APPENDICES: bool = True  # Include APPENDIX/SCHEDULE sections in extraction

    # DocFormer settings (better for legal documents)
    USE_DOCFORMER_EXTRACTOR: bool = False  # Enable DocFormer extractor (better for legal/financial docs)
    DOCFORMER_MODEL: str = "microsoft/docformer-base"  # DocFormer model to use
    DOCFORMER_DEVICE: str = "cpu"  # Device for DocFormer (cpu or cuda)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()

