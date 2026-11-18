
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


class Settings:

    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_timeout: int = 60
    llm_max_retries: int = 2


    db_path: str = str(DATA_DIR / "app.db")

    query_timeout_sec: float = 5.0
    max_result_rows: int = 200


    max_repair_rounds: int = 3


    schema_top_k: int = 4
    schema_top_n_cols: int = 8


    use_embedding_retrieval: bool = _bool("USE_EMBEDDING_RETRIEVAL", False)


    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "auto")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")

    embedding_weight: float = float(os.getenv("EMBEDDING_WEIGHT", "0.5"))


    enable_hitl: bool = True


    audit_log_path: str = str(DATA_DIR / "audit.log")


settings = Settings()
