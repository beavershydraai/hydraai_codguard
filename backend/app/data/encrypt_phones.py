"""Encrypt the phones stored before encryption: `python -m app.data.encrypt_phones [--apply]`.

Env FIRESTORE_DATABASE and PHONE_ENC_KEY. Orders keep `buyer_phone` / `recipient_phone`, now
encrypted (app/data/phone.py); calls keep `job.target.address` encrypted when it is a phone.
Values already encrypted are left alone, so a second run changes nothing. Without --apply it only
counts what it would change.
"""

import argparse

from app.data.phone import encrypt_phone
from app.data.store import get_store

FIELDS = {"orders": ("buyer_phone", "recipient_phone"), "calls": ("job.target.address",)}


def _get(doc: dict, path: str):
    for key in path.split("."):
        doc = (doc or {}).get(key)
    return doc


def changes(collection: str, doc: dict) -> dict:
    """{field path: encrypted value} for the plain phones of one document."""
    out = {}
    for path in FIELDS[collection]:
        value = _get(doc, path)
        if collection == "calls" and _get(doc, "job.target.kind") != "pstn":
            continue
        if isinstance(value, str) and value and encrypt_phone(value) is not value:
            out[path] = encrypt_phone(value)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()
    db = get_store().client
    for collection in FIELDS:
        pending = [
            (snap.reference, update)
            for snap in db.collection(collection).stream()
            if (update := changes(collection, snap.to_dict()))
        ]
        print(f"{collection}: {len(pending)} documents with plain phones")
        if not args.apply:
            continue
        for i in range(0, len(pending), 400):
            batch = db.batch()
            for ref, update in pending[i : i + 400]:
                batch.update(ref, update)
            batch.commit()
        print(f"{collection}: encrypted {len(pending)}")
    if not args.apply:
        print("Dry run: nothing written. Add --apply to write to Firestore.")


if __name__ == "__main__":
    main()
