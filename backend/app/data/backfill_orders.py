"""Add the inbox's sort fields to orders stored before them:
`python -m app.data.backfill_orders [--apply]` (env FIRESTORE_DATABASE).

The inbox sorts in Firestore on top-level `cod_amount_vnd` and `risk_score` (app/decision/inbox.py),
which intake and scoring now write. An order without them would be left out of those sorts. Orders
that have both are left alone, so a second run changes nothing. Without --apply it only counts.
"""

import argparse

from app.data.orders import cod_amount
from app.data.store import get_store


def changes(doc: dict) -> dict:
    """The missing sort fields of one order."""
    out = {}
    if "cod_amount_vnd" not in doc:
        out["cod_amount_vnd"] = cod_amount(doc)
    if "risk_score" not in doc:
        scoring = doc.get("scoring") or {}
        out["risk_score"] = scoring.get("risk_score") if doc.get("tier") else None
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()
    store = get_store()
    pending = [
        (snap.reference, update)
        for snap in store.orders.stream()
        if (update := changes(snap.to_dict()))
    ]
    print(f"{len(pending)} orders without the sort fields")
    if not args.apply:
        print("Dry run: nothing written. Add --apply to write to Firestore.")
        return
    for i in range(0, len(pending), 400):
        batch = store.client.batch()
        for ref, update in pending[i : i + 400]:
            batch.update(ref, update)
        batch.commit()
    print(f"Updated {len(pending)} orders.")


if __name__ == "__main__":
    main()
