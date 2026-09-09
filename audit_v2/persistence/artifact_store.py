"""Content-addressed original files and job artifacts, scoped by tenant."""

import hashlib
import os
import tempfile
from pathlib import Path


class ArtifactStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("V2_ARTIFACT_ROOT") or ".data/artifacts")
        self.bucket = os.getenv("V2_ARTIFACT_BUCKET")

    def _key(self, tenant: str, digest: str) -> str:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid artifact digest")
        return f"{hashlib.sha256(tenant.encode()).hexdigest()}/{digest}"

    def _client(self):
        import boto3  # type: ignore[import-untyped]  # SDK has no bundled type information

        return boto3.client("s3", endpoint_url=os.getenv("V2_S3_ENDPOINT"))

    def put(self, tenant: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        key = self._key(tenant, digest)
        if self.bucket:
            self._client().put_object(Bucket=self.bucket, Key=key, Body=data)
        else:
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError("Artifact integrity failure")
            else:
                descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        return digest

    def get(self, tenant: str, digest: str) -> bytes:
        key = self._key(tenant, digest)
        data = (
            self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()
            if self.bucket
            else (self.root / key).read_bytes()
        )
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Artifact integrity failure")
        return data
