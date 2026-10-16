"""Model health in words a shop owner understands, and the "Update model" button.

The daily monitor (app/risk/jobs/monitor.py) writes `latest/monitor.json` for each country. This
module turns it, with the trained model's metrics, into one of three states and plain reasons:

- update recommended, when any of these holds:
  - the model catches fewer failed deliveries on recent orders than when it learned
    (`performance.degraded`, a confident drop below its validation PR-AUC);
  - recent orders look different from the orders it learned from (Evidently drift alert);
  - many orders got a delivery result since it learned: at least NEW_OUTCOMES_MIN and
    NEW_OUTCOMES_SHARE of the orders it learned from;
- up to date, otherwise;
- no model, before the first training.

Updating starts the Cloud Run job `codguard-train`, which trains every country again; a new model
replaces the current one only if it is at least as good. The current model keeps scoring meanwhile.
"""

import json
import os
from datetime import UTC, datetime, timedelta

from app.data import branches
from app.risk import artifacts
from app.schemas.dashboard import ModelHealth

NEW_OUTCOMES_MIN = 200
NEW_OUTCOMES_SHARE = 0.25
UPDATE_WINDOW = timedelta(minutes=30)  # an update counts as running for this long at most


class UpdateRunning(Exception):
    """An update started less than UPDATE_WINDOW ago and has not produced a model yet."""


def trained_at(version: str | None) -> datetime | None:
    """The training time in a model version (`v20261015173450`)."""
    try:
        return datetime.strptime(version or "", "v%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _json(path: str, code: str) -> dict | None:
    raw = artifacts.read(path, code)
    return json.loads(raw) if raw else None


def requested_at() -> datetime | None:
    """When the last update was started: Firestore `system/model_update` (the API may write
    there; it only reads the model bucket)."""
    from app.data.store import get_store

    snapshot = get_store().client.collection("system").document("model_update").get()
    return (snapshot.to_dict() or {}).get("at") if snapshot.exists else None


def mark_requested(now: datetime) -> None:
    from app.data.store import get_store

    get_store().client.collection("system").document("model_update").set({"at": now})


def country_health(code: str, now: datetime, requested: datetime | None = None) -> ModelHealth:
    metrics = _json("latest/metrics.json", code)
    if metrics is None:
        return ModelHealth(country=code, status="no_model", reasons=["No model has learned yet."])
    learned = trained_at(metrics.get("version"))
    monitor = _json("latest/monitor.json", code) or {}
    reasons = []
    if (monitor.get("performance") or {}).get("degraded"):
        reasons.append(
            "It catches fewer failed deliveries on recent orders than when it last learned."
        )
    if (monitor.get("drift") or {}).get("alert"):
        reasons.append("Recent orders look different from the orders it learned from.")
    new = monitor.get("new_outcomes")
    rows = metrics.get("rows") or 0
    if new is not None and new >= max(NEW_OUTCOMES_MIN, NEW_OUTCOMES_SHARE * rows):
        reasons.append(f"{new:,} orders got a delivery result since it last learned.")
    updating = bool(
        requested and (learned is None or requested > learned) and now - requested < UPDATE_WINDOW
    )
    checked = monitor.get("checked_at")
    return ModelHealth(
        country=code,
        status="update_recommended" if reasons else "up_to_date",
        reasons=reasons,
        trained_at=learned,
        training_orders=rows or None,
        lift_top20=(metrics.get("candidate") or {}).get("lift_top20"),
        checked_at=datetime.fromisoformat(checked) if checked else None,
        new_outcomes=new,
        updating=updating,
    )


def model_health(now: datetime) -> list[ModelHealth]:
    requested = requested_at()
    return [country_health(code, now, requested) for code in branches.countries()]


def start_training() -> None:
    """Run the Cloud Run job `codguard-train` (every country) with the caller's credentials."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    region = os.environ.get("REGION", "asia-southeast1")
    job = os.environ.get("TRAIN_JOB", "codguard-train")
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"
    AuthorizedSession(creds).post(url).raise_for_status()


def request_update(now: datetime) -> list[ModelHealth]:
    """Start one update of every country's model, unless one is already running."""
    if any(h.updating for h in model_health(now)):
        raise UpdateRunning
    start_training()
    mark_requested(now)
    return model_health(now)
