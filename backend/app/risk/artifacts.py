"""Model files: gs://{MODEL_BUCKET}/models/{FIRESTORE_DATABASE}/{country}/ (v{timestamp}/, latest/).

Models are kept per database, so a model trained on synthetic data never serves real orders, and
per country, so orders from different countries are never trained or scored together.
Set MODEL_DIR to a local folder to run the jobs and the engine without Cloud Storage.
The bucket is private to the project; pickles are only ever loaded from it.
"""

import os
import pathlib
from functools import lru_cache


def prefix(country: str = "VN") -> str:
    return f"models/{os.environ.get('FIRESTORE_DATABASE', '(default)')}/{country}"


@lru_cache
def _bucket():
    from google.cloud import storage

    return storage.Client().bucket(os.environ["MODEL_BUCKET"])


def read(path: str, country: str = "VN") -> bytes | None:
    """Bytes of `path` under the country's prefix, or None if it does not exist."""
    local = os.environ.get("MODEL_DIR")
    if local:
        file = pathlib.Path(local, prefix(country), path)
        return file.read_bytes() if file.exists() else None
    blob = _bucket().blob(f"{prefix(country)}/{path}")
    return blob.download_as_bytes() if blob.exists() else None


def write(path: str, data: bytes, country: str = "VN") -> str:
    local = os.environ.get("MODEL_DIR")
    if local:
        file = pathlib.Path(local, prefix(country), path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        return str(file)
    _bucket().blob(f"{prefix(country)}/{path}").upload_from_string(data)
    return f"gs://{os.environ['MODEL_BUCKET']}/{prefix(country)}/{path}"
