"""Mirror the local store to a bucket or another folder, and pull other machines' data back.

    gs://bucket/prefix      Google Cloud Storage   pip install tokentrail[gcs]   (uses your gcloud / ADC login)
    s3://bucket/prefix      AWS S3 or compatible   pip install tokentrail[s3]    (uses your AWS credentials;
                                                    set AWS_ENDPOINT_URL for MinIO, R2 and other S3-compatible stores)
    file:///path or a path  Another folder (a network drive, a synced folder, or tests)

The local store stays the system of record: push uploads this machine's changed files (by content hash, so an
unchanged file is never re-sent); pull downloads other machines' files, and any of this machine's files that are
missing locally (restoring a wiped store). With redact on (the default), prompt text and titles are removed from
run files before upload.
"""
from __future__ import annotations

import hashlib
import json
import os

from .store import FORMAT, NOT_SENT_REMOTE, read_json, write_json


class FileBackend:
    def __init__(self, root: str):
        self.root = os.path.expanduser(root)

    def list(self, prefix: str) -> dict[str, str]:
        out, top = {}, os.path.join(self.root, prefix)
        for dirpath, _, names in os.walk(top):
            for n in names:
                if n.endswith(".json"):
                    full = os.path.join(dirpath, n)
                    with open(full, "rb") as fh:
                        out[os.path.relpath(full, self.root).replace(os.sep, "/")] = hashlib.md5(fh.read()).hexdigest()
        return out

    def get(self, rel: str) -> bytes:
        with open(os.path.join(self.root, rel), "rb") as fh:
            return fh.read()

    def put(self, rel: str, data: bytes) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)


class GCSBackend:
    def __init__(self, bucket: str, prefix: str):
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise SystemExit("gs:// needs the Google Cloud Storage client: pip install 'tokentrail[gcs]'") from exc
        self.bucket = storage.Client().bucket(bucket)
        self.prefix = prefix.strip("/")

    def _key(self, rel: str) -> str:
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def list(self, prefix: str) -> dict[str, str]:
        import base64
        out = {}
        for blob in self.bucket.client.list_blobs(self.bucket, prefix=self._key(prefix)):
            rel = blob.name[len(self.prefix) + 1:] if self.prefix else blob.name
            out[rel] = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
        return out

    def get(self, rel: str) -> bytes:
        return self.bucket.blob(self._key(rel)).download_as_bytes()

    def put(self, rel: str, data: bytes) -> None:
        self.bucket.blob(self._key(rel)).upload_from_string(data, content_type="application/json")


class S3Backend:
    def __init__(self, bucket: str, prefix: str):
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit("s3:// needs boto3: pip install 'tokentrail[s3]'") from exc
        self.client = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _key(self, rel: str) -> str:
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def list(self, prefix: str) -> dict[str, str]:
        out = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(self.prefix) + 1:] if self.prefix else obj["Key"]
                out[rel] = obj.get("ETag", "").strip('"')       # the MD5 for single-part uploads, which these are
        return out

    def get(self, rel: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(rel))["Body"].read()

    def put(self, rel: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(rel), Body=data, ContentType="application/json")


def backend_for(uri: str):
    if uri.startswith("gs://"):
        bucket, _, prefix = uri[5:].partition("/")
        return GCSBackend(bucket, prefix)
    if uri.startswith("s3://"):
        bucket, _, prefix = uri[5:].partition("/")
        return S3Backend(bucket, prefix)
    if uri.startswith("file://"):
        return FileBackend(uri[7:])
    if "://" in uri:
        raise SystemExit(f"unsupported remote: {uri} (use gs://, s3://, file:// or a folder path)")
    return FileBackend(uri)


def redact(rel: str, data: bytes) -> bytes:
    """Remove prompt text and titles from a run file; everything else (counts, tokens, tools) is kept."""
    if "/runs/" not in rel:
        return data
    doc = json.loads(data)
    for r in doc.get("runs", []):
        if r.get("prompt") or r.get("title"):
            r["prompt"], r["title"], r["redacted"] = "", "", True
    return json.dumps(doc, separators=(",", ":")).encode()


class Mirror:
    def __init__(self, store, uri: str, redact_prompts: bool = True, backend=None):
        self.store = store
        self.uri = uri
        self.redact_prompts = redact_prompts
        self.backend = backend or backend_for(uri)
        self.state_path = os.path.join(store.root, ".mirror-state.json")   # outside v1/, never uploaded

    def _state(self) -> dict:
        return read_json(self.state_path, {}) or {}

    def push(self) -> int:
        """Upload this machine's changed files. Returns how many were sent."""
        state = self._state()
        sent = state.setdefault("sent", {})
        n = 0
        mine = f"{FORMAT}/{self.store.machine}/"
        for rel in self.store.files():
            if not rel.startswith(mine) or rel.rsplit("/", 1)[-1] in NOT_SENT_REMOTE:
                continue
            with open(os.path.join(self.store.root, rel), "rb") as fh:
                data = fh.read()
            if self.redact_prompts:
                data = redact(rel, data)
            digest = hashlib.md5(data).hexdigest()
            if sent.get(rel) == digest:
                continue
            self.backend.put(rel, data)
            sent[rel] = digest
            n += 1
        if n:
            write_json(self.state_path, state)
        return n

    def pull(self) -> int:
        """Download other machines' new or changed files, and this machine's files missing locally."""
        state = self._state()
        got = state.setdefault("got", {})
        mine = f"{FORMAT}/{self.store.machine}/"
        n = 0
        for rel, digest in self.backend.list(FORMAT + "/").items():
            if not rel.endswith(".json"):
                continue
            local = os.path.join(self.store.root, rel)
            if rel.startswith(mine):
                if os.path.exists(local):
                    continue                     # local is the system of record for this machine
            elif got.get(rel) == digest and os.path.exists(local):
                continue
            data = self.backend.get(rel)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local + ".tmp", "wb") as fh:
                fh.write(data)
            os.replace(local + ".tmp", local)
            got[rel] = digest
            n += 1
        if n:
            write_json(self.state_path, state)
        return n
