import sys

import pytest

from app.config import Settings, get_settings
from app.repository import MemoryRepository, create_repository
from app.services.storage import StorageService


STRICT_ENV_KEYS = [
    "CRAMLY_ENV",
    "JWT_SECRET",
    "DATABASE_URL",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_BUCKET",
    "CORS_ORIGINS",
    "CORS_ORIGIN_REGEX",
]


def _settings(**overrides):
    values = {
        "openai_api_key": None,
        "openai_model": "test-chat",
        "openai_embedding_model": "test-embed",
        "database_url": None,
        "s3_endpoint_url": None,
        "s3_access_key_id": None,
        "s3_secret_access_key": None,
        "s3_bucket": "test",
        "cors_origins": [],
        "local_storage_path": "storage",
        "jwt_secret": "test-secret",
        "access_token_minutes": 60,
        "env": "development",
        "allow_demo_mode": True,
    }
    values.update(overrides)
    return Settings(**values)


def _clear_strict_env(monkeypatch):
    for key in STRICT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _set_valid_production_env(monkeypatch):
    _clear_strict_env(monkeypatch)
    monkeypatch.setenv("CRAMLY_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "prod-test-jwt-secret-value-123456")
    monkeypatch.setenv("DATABASE_URL", "postgresql://cramly:cramly@postgres:5432/cramly")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "minioadmin-secret")
    monkeypatch.setenv("S3_BUCKET", "cramly-uploads")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_strict_env_allows_memory_repository_fallback(env):
    repo = create_repository(_settings(env=env, database_url=None))

    assert isinstance(repo, MemoryRepository)


def test_production_without_database_url_fails_clearly(monkeypatch):
    _set_valid_production_env(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required when CRAMLY_ENV=production"):
        get_settings()


def test_production_with_weak_jwt_secret_fails_clearly(monkeypatch):
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")

    with pytest.raises(RuntimeError, match="JWT_SECRET must be at least"):
        get_settings()


def test_production_requires_explicit_cors(monkeypatch):
    _set_valid_production_env(monkeypatch)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)

    with pytest.raises(RuntimeError, match="CORS_ORIGINS or CORS_ORIGIN_REGEX is required"):
        get_settings()


def test_production_s3_save_failure_does_not_write_local_files(monkeypatch, tmp_path):
    class FailingS3Client:
        def list_buckets(self):
            return {"Buckets": [{"Name": "cramly-uploads"}]}

        def put_object(self, **kwargs):
            raise RuntimeError("simulated s3 failure")

    class FakeBoto3:
        def client(self, *args, **kwargs):
            return FailingS3Client()

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())
    settings = _settings(
        env="production",
        local_storage_path=str(tmp_path),
        jwt_secret="prod-test-jwt-secret-value-123456",
        database_url="postgresql://cramly:cramly@postgres:5432/cramly",
        s3_endpoint_url="http://minio:9000",
        s3_access_key_id="minioadmin",
        s3_secret_access_key="minioadmin-secret",
        s3_bucket="cramly-uploads",
    )

    with pytest.raises(RuntimeError, match="S3 save failed"):
        StorageService(settings).save("notes.txt", b"hello")

    assert list(tmp_path.rglob("*")) == []
