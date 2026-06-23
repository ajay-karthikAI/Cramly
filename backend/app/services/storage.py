from __future__ import annotations

from pathlib import Path
import uuid

from app.config import Settings


class StorageService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def save(self, filename: str, content: bytes) -> str:
        key = f"uploads/{uuid.uuid4()}-{Path(filename).name}"
        if self._can_use_s3():
            try:
                import boto3

                client = boto3.client(
                    "s3",
                    endpoint_url=self.settings.s3_endpoint_url,
                    aws_access_key_id=self.settings.s3_access_key_id,
                    aws_secret_access_key=self.settings.s3_secret_access_key,
                )
                _ensure_bucket(client, self.settings.s3_bucket)
                client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=content)
                return f"s3://{self.settings.s3_bucket}/{key}"
            except Exception as exc:
                if self.settings.is_strict_env:
                    raise RuntimeError(
                        f"S3 save failed when CRAMLY_ENV={self.settings.env}; "
                        "refusing to fall back to local disk."
                    ) from exc
        elif self.settings.is_strict_env:
            raise RuntimeError(
                f"S3 settings are required when CRAMLY_ENV={self.settings.env} and uploads are enabled."
            )

        root = Path(self.settings.local_storage_path)
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def _can_use_s3(self) -> bool:
        return bool(
            self.settings.s3_endpoint_url
            and self.settings.s3_access_key_id
            and self.settings.s3_secret_access_key
            and self.settings.s3_bucket
        )


def _ensure_bucket(client, bucket: str) -> None:
    existing = [item["Name"] for item in client.list_buckets().get("Buckets", [])]
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
