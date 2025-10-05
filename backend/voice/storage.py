"""Adapters for persisting call recordings to object storage."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import structlog

try:  # pragma: no cover - optional dependency
    import boto3
except Exception:  # pragma: no cover
    boto3 = None  # type: ignore

from backend.app.config import Settings
from backend.db.models import CallSession

logger = structlog.get_logger(__name__)


class CallStorageAdapter:
    """Upload call recordings and generate presigned URLs."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None,
        endpoint: str | None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint = endpoint
        if boto3 is None:
            logger.warning("voice.storage.boto_missing")
            self._client = None
        else:
            self._client = boto3.client(  # type: ignore[attr-defined]
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint,
            )
        # TODO: support SSE configuration / retention policies

    def upload(self, session: CallSession, file_path: Path) -> str:
        if self._client is None:
            logger.info("voice.storage.stub_upload", call_session_id=str(session.id))
            return ""
        if not file_path.exists():
            logger.warning(
                "voice.storage.file_missing",
                call_session_id=str(session.id),
                path=str(file_path),
            )
            return ""
        object_key = self._build_object_key(session, file_path)
        with file_path.open("rb") as handle:
            self._client.upload_fileobj(handle, self._bucket, object_key)  # type: ignore[attr-defined]
        logger.info(
            "voice.storage.uploaded",
            call_session_id=str(session.id),
            object_key=object_key,
        )
        return object_key

    def presign(self, object_key: str, *, expires_seconds: int = 3600) -> str:
        if self._client is None or not object_key:
            return ""
        try:
            url = self._client.generate_presigned_url(  # type: ignore[attr-defined]
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_seconds,
            )
            return url
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("voice.storage.presign_failed", object_key=object_key, error=str(exc))
            return ""

    def _build_object_key(self, session: CallSession, file_path: Path) -> str:
        timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        sanitized = file_path.name.replace(" ", "_")
        return f"calls/{session.id}/{timestamp}-{sanitized}"


class NullCallStorageAdapter:
    """No-op storage adapter when bucket configuration is absent."""

    def upload(self, session: CallSession, file_path: Path) -> str:  # type: ignore[override]
        logger.info("voice.storage.disabled", call_session_id=str(session.id))
        return ""

    def presign(self, object_key: str, *, expires_seconds: int = 3600) -> str:  # type: ignore[override]
        return ""


def build_call_storage_adapter(settings: Settings) -> CallStorageAdapter | NullCallStorageAdapter:
    storage_cfg = settings.call_storage_config()
    if not storage_cfg.bucket:
        logger.warning("voice.storage.not_configured")
        return NullCallStorageAdapter()
    return CallStorageAdapter(
        bucket=storage_cfg.bucket,
        region=storage_cfg.region,
        endpoint=str(storage_cfg.endpoint) if storage_cfg.endpoint else None,
    )


__all__ = ["CallStorageAdapter", "NullCallStorageAdapter", "build_call_storage_adapter"]
