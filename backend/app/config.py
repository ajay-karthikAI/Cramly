from dataclasses import dataclass
import os
from pathlib import Path


CHAT_QUESTION_MAX_LENGTH = 4000
TOPIC_MAX_LENGTH = 300
LOCAL_JWT_SECRET = "change-me-in-production"
LOCAL_CORS_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:\d+)?"
ALLOWED_ENVS = {"development", "test", "beta", "production"}
STRICT_ENVS = {"beta", "production"}
WEAK_JWT_SECRETS = {
    LOCAL_JWT_SECRET,
    "change-this-local-secret",
    "test-secret",
    "secret",
}
MIN_STRICT_JWT_SECRET_LENGTH = 32


try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ModuleNotFoundError:
    pass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_embedding_model: str
    database_url: str | None
    s3_endpoint_url: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_bucket: str
    cors_origins: list[str]
    local_storage_path: str
    jwt_secret: str
    access_token_minutes: int
    env: str = "development"
    allow_demo_mode: bool = False
    cors_origin_regex: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    max_extracted_text_chars: int = 250_000
    max_document_chunks: int = 300
    max_pdf_pages: int = 80
    max_ocr_pages: int = 10
    daily_chat_limit: int = 200
    daily_upload_limit: int = 25
    daily_generation_limit: int = 100
    rate_limit_window_seconds: int = 60
    auth_rate_limit_per_minute: int = 20
    ai_rate_limit_per_minute: int = 60
    enable_dev_rag: bool = False
    invite_code: str | None = None

    @property
    def demo_mode(self) -> bool:
        return self.allow_demo_mode

    @property
    def is_strict_env(self) -> bool:
        return self.env in STRICT_ENVS


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() == "true"


def get_settings() -> Settings:
    env = (os.getenv("CRAMLY_ENV", "development").strip().lower() or "development")
    is_strict_env = env in STRICT_ENVS
    origins_raw = os.getenv("CORS_ORIGINS")
    origins_default = None if is_strict_env else "http://localhost:3000"
    origins = (origins_raw if origins_raw is not None else origins_default or "").split(",")
    cors_origin_regex = os.getenv("CORS_ORIGIN_REGEX")
    if cors_origin_regex is None and not is_strict_env:
        cors_origin_regex = LOCAL_CORS_ORIGIN_REGEX

    jwt_secret_env = os.getenv("JWT_SECRET")
    s3_bucket_env = os.getenv("S3_BUCKET")
    settings = Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        database_url=os.getenv("DATABASE_URL"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        s3_bucket=s3_bucket_env or "cramly-uploads",
        cors_origins=[origin.strip() for origin in origins if origin.strip()],
        cors_origin_regex=cors_origin_regex,
        local_storage_path=os.getenv("LOCAL_STORAGE_PATH", "storage"),
        jwt_secret=jwt_secret_env or LOCAL_JWT_SECRET,
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "10080")),
        env=env,
        allow_demo_mode=os.getenv("CRAMLY_ALLOW_DEMO_MODE", "false").lower() == "true",
        max_upload_bytes=_int_env("CRAMLY_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        max_extracted_text_chars=_int_env("CRAMLY_MAX_EXTRACTED_TEXT_CHARS", 250_000),
        max_document_chunks=_int_env("CRAMLY_MAX_DOCUMENT_CHUNKS", 300),
        max_pdf_pages=_int_env("CRAMLY_MAX_PDF_PAGES", 80),
        max_ocr_pages=_int_env("CRAMLY_MAX_OCR_PAGES", 10),
        daily_chat_limit=_int_env("CRAMLY_DAILY_CHAT_LIMIT", 200),
        daily_upload_limit=_int_env("CRAMLY_DAILY_UPLOAD_LIMIT", 25),
        daily_generation_limit=_int_env("CRAMLY_DAILY_GENERATION_LIMIT", 100),
        rate_limit_window_seconds=_int_env("CRAMLY_RATE_LIMIT_WINDOW_SECONDS", 60),
        auth_rate_limit_per_minute=_int_env("CRAMLY_AUTH_RATE_LIMIT_PER_MINUTE", 20),
        ai_rate_limit_per_minute=_int_env("CRAMLY_AI_RATE_LIMIT_PER_MINUTE", 60),
        enable_dev_rag=_bool_env("CRAMLY_ENABLE_DEV_RAG", False),
        invite_code=(os.getenv("CRAMLY_INVITE_CODE") or "").strip() or None,
    )
    _validate_settings(
        settings,
        jwt_secret_configured=bool(jwt_secret_env and jwt_secret_env.strip()),
        s3_bucket_configured=bool(s3_bucket_env and s3_bucket_env.strip()),
    )
    return settings


def _validate_settings(settings: Settings, *, jwt_secret_configured: bool, s3_bucket_configured: bool) -> None:
    errors: list[str] = []
    if settings.env not in ALLOWED_ENVS:
        allowed = ", ".join(sorted(ALLOWED_ENVS))
        errors.append(f"CRAMLY_ENV must be one of {allowed}.")

    if settings.is_strict_env:
        env_label = f"CRAMLY_ENV={settings.env}"
        if not jwt_secret_configured:
            errors.append(f"JWT_SECRET is required when {env_label}.")
        elif _is_weak_jwt_secret(settings.jwt_secret):
            errors.append(
                f"JWT_SECRET must be at least {MIN_STRICT_JWT_SECRET_LENGTH} characters "
                f"and not use a local default when {env_label}."
            )

        if not settings.database_url:
            errors.append(f"DATABASE_URL is required when {env_label}.")

        missing_s3 = [
            name
            for name, value in (
                ("S3_ENDPOINT_URL", settings.s3_endpoint_url),
                ("S3_ACCESS_KEY_ID", settings.s3_access_key_id),
                ("S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
            )
            if not value
        ]
        if not s3_bucket_configured:
            missing_s3.append("S3_BUCKET")
        if missing_s3:
            missing = ", ".join(missing_s3)
            errors.append(f"{missing} must be configured when {env_label} and uploads are enabled.")

        if not settings.cors_origins and not settings.cors_origin_regex:
            errors.append(f"CORS_ORIGINS or CORS_ORIGIN_REGEX is required when {env_label}.")

    if errors:
        raise RuntimeError("Invalid Cramly configuration: " + " ".join(errors))


def _is_weak_jwt_secret(secret: str) -> bool:
    stripped = secret.strip()
    return stripped in WEAK_JWT_SECRETS or len(stripped) < MIN_STRICT_JWT_SECRET_LENGTH
