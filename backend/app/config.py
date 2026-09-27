"""OpsMind backend settings, read once from environment variables."""
import os
from dataclasses import dataclass

DEFAULT_VERIFY_TIMEOUT_SECONDS = 150
DEFAULT_VERIFY_POLL_SECONDS = 10
DEFAULT_VERIFY_P95_TARGET_SECONDS = 0.5
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 120
DEFAULT_EVIDENCE_WINDOW_MINUTES = 5
DEFAULT_DEPLOY_LOOKBACK_MINUTES = 60


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    prometheus_url: str
    product_api_url: str
    product_api_log_file: str
    hindsight_url: str
    hindsight_bank: str
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str
    slack_bot_token: str
    slack_app_token: str
    slack_channel_id: str
    dashboard_url: str
    runbooks_dir: str
    ansible_dir: str
    execution_timeout_seconds: int
    verify_timeout_seconds: int
    verify_poll_seconds: int
    verify_p95_target_seconds: float
    evidence_window_minutes: int
    deploy_lookback_minutes: int
    is_background_enabled: bool


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://localhost:5432/opsmind"),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://prometheus:9090"),
        product_api_url=os.getenv("PRODUCT_API_URL", "http://product-api:8000"),
        product_api_log_file=os.getenv("PRODUCT_API_LOG_FILE", "/var/log/product-api/app.log"),
        hindsight_url=os.getenv("HINDSIGHT_URL", "http://hindsight:8888"),
        hindsight_bank=os.getenv("HINDSIGHT_BANK", "opsmind-sre"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
        slack_app_token=os.getenv("SLACK_APP_TOKEN", ""),
        slack_channel_id=os.getenv("SLACK_CHANNEL_ID", ""),
        dashboard_url=os.getenv("DASHBOARD_URL", "http://127.0.0.1:3002"),
        runbooks_dir=os.getenv("RUNBOOKS_DIR", "/opsmind/runbooks"),
        ansible_dir=os.getenv("ANSIBLE_DIR", "/opsmind/ansible"),
        execution_timeout_seconds=int(os.getenv("EXECUTION_TIMEOUT_SECONDS", DEFAULT_EXECUTION_TIMEOUT_SECONDS)),
        verify_timeout_seconds=int(os.getenv("VERIFY_TIMEOUT_SECONDS", DEFAULT_VERIFY_TIMEOUT_SECONDS)),
        verify_poll_seconds=int(os.getenv("VERIFY_POLL_SECONDS", DEFAULT_VERIFY_POLL_SECONDS)),
        verify_p95_target_seconds=float(os.getenv("VERIFY_P95_TARGET_SECONDS", DEFAULT_VERIFY_P95_TARGET_SECONDS)),
        evidence_window_minutes=int(os.getenv("EVIDENCE_WINDOW_MINUTES", DEFAULT_EVIDENCE_WINDOW_MINUTES)),
        deploy_lookback_minutes=int(os.getenv("DEPLOY_LOOKBACK_MINUTES", DEFAULT_DEPLOY_LOOKBACK_MINUTES)),
        is_background_enabled=_bool("BACKGROUND_ENABLED", True),
    )
