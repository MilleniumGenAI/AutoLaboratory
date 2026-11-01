"""`trial` subcommand: start a durable trial, wait for its recorded result, or read worker status."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from ..errors import LabError
from ..sqlite_store import SQLiteStore
from ..state import _runs
from .common import (
    enqueue_and_start_operation,
    explicit_confirmation,
    normalize_trial_hypothesis,
    resolve_config,
)

HYPOTHESIS_HINT = (
    "Run: python scripts/lab.py --agent --config <path> trial start --hypothesis-json "
    "'{\"title\":\"...\",\"observation\":\"...\",\"expected_effect\":\"...\"}'"
)
_DURABLE_FIELDS = frozenset({
    "title", "observation", "expected_effect", "evidence",
    "falsification", "rationale", "target_files", "delegation",
})


def _wait_for_sqlite_trial(store: SQLiteStore, lab_id: uuid.UUID, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        operation = store.load_worker(lab_id)
        if operation is None or operation.get("kind") != "trial":
            return {"pending": True}
        status = operation.get("status")
        if status == "succeeded":
            result = operation.get("result")
            if isinstance(result, dict):
                return result.get("manifest") if isinstance(result.get("manifest"), dict) else result
            return {"operation_id": str(operation["operation_id"]), "status": status}
        if status == "failed":
            raise LabError("Background trial failed; inspect its recorded job result", code="E_WORKER_FAILED")
        if status == "recovery_required":
            raise LabError("Background trial stopped before recording a result", code="E_WORKER_DIED",
                           hint="Run explicit recovery before retrying")
        if time.monotonic() >= deadline:
            return {"pending": True, "operation_id": str(operation["operation_id"]), "status": status}
        time.sleep(min(0.2, max(0.01, deadline - time.monotonic())))


def _hypothesis_from_args(args: Any) -> dict[str, Any] | None:
    """Return the raw hypothesis from --hypothesis-json or the inline flags, or None when neither was given."""
    raw_json = getattr(args, "hypothesis_json", None)
    if raw_json is not None:
        try:
            parsed = json.loads(str(raw_json))
        except ValueError as error:
            raise LabError(f"Hypothesis JSON is invalid: {error}", code="E_BAD_HYPOTHESIS") from error
        if not isinstance(parsed, dict):
            raise LabError("Hypothesis JSON must be an object", code="E_BAD_HYPOTHESIS")
        return parsed

    inline = {name: getattr(args, name, None) for name in ("title", "observation", "expected_effect")}
    if all(value is None for value in inline.values()):
        return None
    payload: dict[str, Any] = {name: (value or "").strip() for name, value in inline.items()}
    for name in ("rationale", "falsification"):
        value = getattr(args, name, None)
        if value:
            payload[name] = str(value).strip()
    if getattr(args, "target_files", None):
        payload["target_files"] = list(args.target_files)
    return payload


def _durable_hypothesis(args: Any) -> dict[str, Any]:
    raw = _hypothesis_from_args(args)
    if raw is None:
        raise LabError(
            "A hypothesis is required (--hypothesis-json, or --title/--observation/--expected-effect)",
            code="E_HYPOTHESIS_REQUIRED",
            hint=HYPOTHESIS_HINT,
        )
    durable = {key: value for key, value in raw.items() if key in _DURABLE_FIELDS}
    try:
        return normalize_trial_hypothesis(durable)
    except ValueError as error:
        raise LabError(str(error), code="E_CONTRACT_HYPOTHESIS", hint=HYPOTHESIS_HINT) from error


def _add_hypothesis_arguments(parser: Any) -> None:
    parser.add_argument("--hypothesis-json", type=str, default=None, help="Inline JSON object for the hypothesis")
    parser.add_argument("--title", type=str, default=None, help="Inline hypothesis title")
    parser.add_argument("--observation", type=str, default=None, help="Inline hypothesis observation")
    parser.add_argument("--expected-effect", type=str, default=None, help="Inline hypothesis expected effect")
    parser.add_argument("--rationale", type=str, default=None, help="Optional inline hypothesis rationale")
    parser.add_argument("--falsification", type=str, default=None, help="Optional inline hypothesis falsification criterion")
    parser.add_argument("--target-files", nargs="*", default=None, help="Optional target files for inline hypothesis")


def register(subparsers: Any) -> None:
    trial = subparsers.add_parser("trial")
    commands = trial.add_subparsers(dest="trial_command", required=True)
    # Disable prefix matching so `--hypothesis <file>` is refused rather than read as `--hypothesis-json`.
    start = commands.add_parser("start", allow_abbrev=False)
    _add_hypothesis_arguments(start)
    wait = commands.add_parser("wait")
    wait.add_argument("--timeout", type=float, default=30.0)
    commands.add_parser("status")


def run(args: Any, labs_root: Path | None) -> dict[str, Any]:
    config = resolve_config(args, labs_root, pending_ok=False)
    store = SQLiteStore()
    lab_id = uuid.UUID(str(config.lab_id))
    action = args.trial_command
    if action == "status":
        worker = store.load_worker(lab_id)
        return {"worker": worker, "running_manifests": [
            item["id"] for item in _runs(config) if item.get("status") == "running"
        ]}
    if action == "wait":
        return _wait_for_sqlite_trial(store, lab_id, float(args.timeout))

    hypothesis = _durable_hypothesis(args)
    operation = enqueue_and_start_operation(
        lab_id, "trial", {"hypothesis": hypothesis, **explicit_confirmation(args)},
        f"cli-trial-{uuid.uuid4()}",
    )
    return {
        "started": operation.get("status") in {"queued", "running", "finalizing"},
        "operation_id": str(operation["operation_id"]),
        "status": operation.get("status"),
    }
