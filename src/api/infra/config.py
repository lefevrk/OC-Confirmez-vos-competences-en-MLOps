"""Environment-backed service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, supplied by the environment or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # MLflow connection
    mlflow_tracking_uri: str
    mlflow_tracking_username: str
    mlflow_tracking_password: str

    # PostgreSQL prediction-event storage
    database_url: str

    # Registered serving model
    model_name: str = "credit_scoring"
    model_alias: str = "champion"

    # Logging
    log_level: str = "INFO"

    # API authentication — empty disables it, useful for local development
    api_token: str = ""

    # Directory the drift report is read from (see scripts/generate_drift_report.py)
    reports_dir: str = "reports"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide immutable configuration."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
