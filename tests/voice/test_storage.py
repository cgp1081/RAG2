from __future__ import annotations

import uuid
from types import SimpleNamespace

from backend.voice import storage as storage_module
from backend.voice.storage import (
    CallStorageAdapter,
    NullCallStorageAdapter,
    build_call_storage_adapter,
)


class FakeClient:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str]] = []

    def upload_fileobj(self, fileobj, bucket: str, key: str) -> None:
        fileobj.read()
        self.uploaded.append((bucket, key))

    def generate_presigned_url(self, *_args, **_kwargs) -> str:
        return "https://storage.fake/presigned"


def test_upload_and_presign(monkeypatch, tmp_path):
    fake_client = FakeClient()
    monkeypatch.setattr(
        storage_module,
        "boto3",
        SimpleNamespace(client=lambda **_: fake_client),
    )

    adapter = CallStorageAdapter(bucket="bucket", region="us-west-2", endpoint=None)
    call = SimpleNamespace(id=uuid.uuid4())  # type: ignore[name-defined]
    file_path = tmp_path / "call.wav"
    file_path.write_bytes(b"audio")

    object_key = adapter.upload(call, file_path)  # type: ignore[arg-type]
    assert object_key.endswith("call.wav")
    assert fake_client.uploaded
    url = adapter.presign(object_key)
    assert url == "https://storage.fake/presigned"


def test_null_adapter(monkeypatch, tmp_path):
    adapter = NullCallStorageAdapter()
    call = SimpleNamespace(id=uuid.uuid4())  # type: ignore[name-defined]
    file_path = tmp_path / "missing.wav"
    key = adapter.upload(call, file_path)  # type: ignore[arg-type]
    assert key == ""
    assert adapter.presign("key") == ""


def test_build_adapter_without_bucket(monkeypatch, test_settings):
    test_settings.call_storage_bucket = None
    adapter = build_call_storage_adapter(test_settings)
    assert isinstance(adapter, NullCallStorageAdapter)
