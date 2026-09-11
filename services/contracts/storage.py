from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError  # type: ignore[import-untyped]

from services.api.config import get_settings


class ObjectStoreUnavailable(RuntimeError):
    """The deployment has not configured its private contract object bucket."""


class ObjectStoreVerificationError(RuntimeError):
    """A private object is absent or does not match its upload grant."""


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]


def _client() -> Any:
    import boto3  # type: ignore[import-untyped]

    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


def create_private_upload(
    *, object_key: str, mime_type: str, size_bytes: int, sha256: str | None = None, expires_in: int | None = None
) -> PresignedUpload:
    settings = get_settings()
    if not settings.contract_object_bucket:
        raise ObjectStoreUnavailable("Contract object storage is not configured")
    expires = expires_in or settings.contract_object_url_expiry_seconds
    fields: dict[str, str] = {"Content-Type": mime_type}
    conditions: list[object] = [{"Content-Type": mime_type}, ["content-length-range", size_bytes, size_bytes]]
    if sha256:
        fields["x-amz-meta-sha256"] = sha256
        conditions.append({"x-amz-meta-sha256": sha256})
    if settings.contract_object_kms_key_arn:
        fields["x-amz-server-side-encryption"] = "aws:kms"
        fields["x-amz-server-side-encryption-aws-kms-key-id"] = settings.contract_object_kms_key_arn
        conditions.extend([
            {"x-amz-server-side-encryption": "aws:kms"},
            {"x-amz-server-side-encryption-aws-kms-key-id": settings.contract_object_kms_key_arn},
        ])
    try:
        result = _client().generate_presigned_post(
            settings.contract_object_bucket,
            object_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires,
        )
    except BotoCoreError as exc:
        if settings.environment == "development":
            raise ObjectStoreUnavailable("Private object storage credentials are unavailable") from exc
        raise
    return PresignedUpload(url=result["url"], fields={str(key): str(value) for key, value in result["fields"].items()})


def create_private_download(*, object_key: str, expires_in: int | None = None) -> str:
    settings = get_settings()
    if not settings.contract_object_bucket:
        raise ObjectStoreUnavailable("Contract object storage is not configured")
    expires = expires_in or settings.contract_object_url_expiry_seconds
    return str(
        _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.contract_object_bucket, "Key": object_key},
            ExpiresIn=expires,
        )
    )



def fetch_private_object(
    *,
    object_key: str,
    expected_size_bytes: int,
    expected_mime_type: str,
    expected_sha256: str | None = None,
) -> bytes:
    """Read a private object only after validating its stored S3 headers."""
    settings = get_settings()
    if not settings.contract_object_bucket:
        raise ObjectStoreUnavailable("Contract object storage is not configured")
    client = _client()
    try:
        head = client.head_object(Bucket=settings.contract_object_bucket, Key=object_key)
        size = int(head.get("ContentLength", -1))
        mime_type = str(head.get("ContentType", ""))
        metadata = {str(key).lower(): str(value) for key, value in (head.get("Metadata") or {}).items()}
        if size != expected_size_bytes:
            raise ObjectStoreVerificationError("Private object size does not match the upload grant")
        if mime_type and mime_type != expected_mime_type:
            raise ObjectStoreVerificationError("Private object MIME type does not match the upload grant")
        if expected_sha256 and metadata.get("sha256") and metadata["sha256"] != expected_sha256:
            raise ObjectStoreVerificationError("Private object metadata checksum does not match")
        response = client.get_object(Bucket=settings.contract_object_bucket, Key=object_key)
        body = bytes(response["Body"].read(expected_size_bytes + 1))
    except ObjectStoreVerificationError:
        raise
    except Exception as exc:
        raise ObjectStoreVerificationError("Private object could not be read") from exc
    if len(body) != expected_size_bytes:
        raise ObjectStoreVerificationError("Private object body size does not match the upload grant")
    if response.get("ContentType") and str(response["ContentType"]) != expected_mime_type:
        raise ObjectStoreVerificationError("Private object response MIME type does not match")
    return body
