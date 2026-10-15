"""Create the composite indexes in infra/firestore.indexes.json that the database lacks.

    python3 .github/scripts/sync_firestore_indexes.py \
        infra/firestore.indexes.json <project> <database>

The file uses the Firebase CLI format. Existing indexes are left alone, and nothing is deleted.
Index builds run in the background and take minutes; a query that needs a new index fails with
FAILED_PRECONDITION until it is ready.
"""

import json
import subprocess
import sys


def field_config(field: dict) -> str:
    if "order" in field:
        return f"field-path={field['fieldPath']},order={field['order'].lower()}"
    return f"field-path={field['fieldPath']},array-config={field['arrayConfig'].lower()}"


def main(path: str, project: str, database: str) -> int:
    with open(path, encoding="utf-8") as f:
        indexes = json.load(f)["indexes"]
    failed = 0
    for index in indexes:
        fields = index["fields"]
        label = f"{index['collectionGroup']}({', '.join(field_config(f) for f in fields)})"
        command = [
            "gcloud",
            "firestore",
            "indexes",
            "composite",
            "create",
            "--project",
            project,
            "--database",
            database,
            "--collection-group",
            index["collectionGroup"],
            "--query-scope",
            index.get("queryScope", "COLLECTION"),
            "--async",
            "--quiet",
        ]
        for field in fields:
            command += ["--field-config", field_config(field)]
        result = subprocess.run(command, capture_output=True, text=True)
        output = result.stdout + result.stderr
        if result.returncode == 0:
            print(f"created (building): {label}")
        elif "already exists" in output.lower() or "ALREADY_EXISTS" in output:
            print(f"exists: {label}")
        else:
            failed += 1
            print(f"::error::Could not create the index {label}: {output.strip()[-500:]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
