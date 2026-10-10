from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    app_name: str = Field(
        default="Sahl Compliance Decoder",
        alias="APP_NAME",
    )

    app_env: str = Field(
        default="development",
        alias="APP_ENV",
    )

    app_host: str = Field(
        default="127.0.0.1",
        alias="APP_HOST",
    )

    app_port: int = Field(
        default=8000,
        alias="APP_PORT",
    )

    openai_api_key: str = Field(
        alias="OPENAI_API_KEY",
    )

    openai_model: str = Field(
        default="gpt-5.6-luna",
        alias="OPENAI_MODEL",
    )

    max_upload_mb: int = Field(
        default=100,
        alias="MAX_UPLOAD_MB",
    )

    max_pdf_pages: int = Field(
        default=1000,
        alias="MAX_PDF_PAGES",
    )

    output_dir: str = Field(
        default="data/outputs",
        alias="OUTPUT_DIR",
    )

    upload_dir: str = Field(
        default="data/uploads",
        alias="UPLOAD_DIR",
    )

    extracted_dir: str = Field(
        default="data/extracted",
        alias="EXTRACTED_DIR",
    )

    processed_dir: str = Field(
        default="data/processed",
        alias="PROCESSED_DIR",
    )

    smtp_host: str = Field(
        default="smtp.gmail.com",
        alias="SMTP_HOST",
    )

    smtp_port: int = Field(
        default=587,
        alias="SMTP_PORT",
    )

    smtp_username: str = Field(
        default="",
        alias="SMTP_USERNAME",
    )

    smtp_password: str = Field(
        default="",
        alias="SMTP_PASSWORD",
    )

    sahl_recipients: str = Field(
        default=(
            "ayesha@getsahl.io,"
            "ayesha@mail.getsahl.io"
        ),
        alias="SAHL_RECIPIENTS",
    )

    send_email_on_decode: bool = Field(
        default=True,
        alias="SEND_EMAIL_ON_DECODE",
    )

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def upload_path(self) -> Path:
        return self.root_dir / self.upload_dir

    @property
    def extracted_path(self) -> Path:
        return self.root_dir / self.extracted_dir

    @property
    def processed_path(self) -> Path:
        return self.root_dir / self.processed_dir

    @property
    def output_path(self) -> Path:
        return self.root_dir / self.output_dir

    def ensure_directories(self) -> None:
        for path in (
            self.upload_path,
            self.extracted_path,
            self.processed_path,
            self.output_path,
        ):
            path.mkdir(
                parents=True,
                exist_ok=True,
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings