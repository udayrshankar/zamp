from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Backend directory (c:\...\backend)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Potential .env locations (backend/.env or root .env)
BACKEND_ENV = BASE_DIR / ".env"
ROOT_ENV = BASE_DIR.parent / ".env"

# Load into os.environ for any external libraries relying on os.getenv
if BACKEND_ENV.is_file():
    load_dotenv(BACKEND_ENV)
elif ROOT_ENV.is_file():
    load_dotenv(ROOT_ENV)


class Settings(BaseSettings):
    # Application Configuration
    APP_NAME: str = "Backend API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Database
    MONGO_DB_URL: str = ""
    MONGO_DB_NAME: str = "zamp_db"

    # Upload limits
    MAX_UPLOAD_MB: int = 20
    MAX_PAGES: int = 50

    # Page routing: when to distrust a PDF's text layer and use OCR instead
    MIN_TEXT_CHARS: int = 50
    MIN_ALNUM_RATIO: float = 0.5
    IMAGE_COVERAGE_THRESHOLD: float = 0.5
    SPARSE_TEXT_CHARS: int = 200

    # Nemotron Parse reads scanned pages. Without a key, local OCR does it instead.
    NVIDIA_KEY: str = ""
    NEMOTRON_PARSE_URL: str = (
        "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"
    )
    NEMOTRON_PARSE_TIMEOUT_SECONDS: float = 60
    # Recommended maximum input resolution for the model
    NEMOTRON_PARSE_MAX_WIDTH: int = 1664
    NEMOTRON_PARSE_MAX_HEIGHT: int = 2048
    # Below this the page goes to local OCR, because the model invents text on
    # near-empty pages. Real invoices measure well above it.
    PARSE_MIN_INK_RATIO: float = 0.001

    # The LLM that detects PO references and compares documents
    LLM_URL: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    LLM_MODEL: str = "nvidia/nemotron-3.5-bolt-e4b"
    LLM_TIMEOUT_SECONDS: float = 45

    # How far billing may run over a PO: up to ACCEPT is accepted, up to REJECT
    # goes to review, and beyond that is rejected.
    ACCEPT_TOLERANCE_PERCENT: float = 2
    REJECT_TOLERANCE_PERCENT: float = 10

    # OCR
    OCR_DPI: int = 300
    LOW_OCR_CONFIDENCE: float = 0.7

    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_ENV), str(ROOT_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Singleton instance that can be imported anywhere
settings = get_settings()

