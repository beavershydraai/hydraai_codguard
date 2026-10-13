"""Model files: gs://{MODEL_BUCKET}/models/{FIRESTORE_DATABASE}/ (v{timestamp}/ and latest/).

Models are kept per database so a model trained on synthetic data never serves real orders.
Set MODEL_DIR to a local folder to run the jobs and the engine without Cloud Storage.
The bucket is private to the project; pickles are only ever loaded from it.
"""

import os
import pathlib
from functools import lru_cache


def prefix() -> str:
    return f"models/{os.environ.get('FIRESTORE_DATABASE', '(default)')}"


@lru_cache
def _bucket():
    from google.cloud import storage

    return storage.Client().bucket(os.environ["MODEL_BUCKET"])


def read(path: str) -> bytes | None:
    """Bytes of `path` under the prefix, or None if it does not exist."""
    local = os.environ.get("MODEL_DIR")
    if local:
        file = pathlib.Path(local, prefix(), path)
        return file.read_bytes() if file.exists() else None
    blob = _bucket().blob(f"{prefix()}/{path}")
    return blob.download_as_bytes() if blob.exists() else None


def write(path: str, data: bytes) -> str:
    local = os.environ.get("MODEL_DIR")
    if local:
        file = pathlib.Path(local, prefix(), path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        return str(file)
    _bucket().blob(f"{prefix()}/{path}").upload_from_string(data)
    return f"gs://{os.environ['MODEL_BUCKET']}/{prefix()}/{path}"
