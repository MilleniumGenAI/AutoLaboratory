"""Measurement contract records and manifest migrations (in memory only)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .config import LabConfig


def migrate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") == 1:
        return manifest
    updated = dict(manifest)
    updated["schema"] = 1
    if "epoch" not in updated:
        updated["epoch"] = 1
    return updated


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    if "epochs" not in state or not isinstance(state.get("epochs"), list):
        state["epochs"] = []
    if "current_epoch" not in state:
        state["current_epoch"] = state["epochs"][-1]["id"] if state["epochs"] else 1
    return state


def epoch_fingerprint(config: LabConfig, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluator": list(config.evaluator),
        "input_hashes": {item["path"]: item["sha256"] for item in state.get("inputs", [])},
        "config_sha256": state["config_sha256"],
    }


def find_epoch(state: dict[str, Any], epoch_id: int) -> dict[str, Any] | None:
    for item in state.get("epochs", []):
        if isinstance(item, dict) and item.get("id") == epoch_id:
            return item
    return None


def ensure_epoch(state: dict[str, Any], config: LabConfig) -> int:
    """Record the lab's contract once, on its first baseline; a lab never opens another one."""
    migrate_state(state)
    if not state["epochs"]:
        state["epochs"].append({
            "id": 1,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "superseded_at": None,
            "supersede_reason": None,
            "previous_epoch_id": None,
            "metrics": {"primary": config.primary, "direction": config.direction},
            "repeats": config.repeats,
            **epoch_fingerprint(config, state),
        })
        state["current_epoch"] = 1
        return 1
    current = int(state["current_epoch"])
    if find_epoch(state, current) is None:
        state["current_epoch"] = state["epochs"][-1]["id"]
    return int(state["current_epoch"])


def record_noise_floor(state: dict[str, Any], config: LabConfig, runs: list[dict[str, Any]]) -> None:
    migrate_state(state)
    epoch = find_epoch(state, int(state["current_epoch"]))
    if epoch is None:
        return
    values = [float(run["metrics"][config.primary]) for run in runs if isinstance(run.get("metrics"), dict)]
    if not values:
        return
    spread = max(values) - min(values)
    floor = {"primary": spread, "metric": config.primary}
    epoch["noise_floor"] = floor
    state["noise_floor"] = floor


def manifest_epoch_id(manifest: dict[str, Any], state: dict[str, Any]) -> int:
    return int(manifest.get("epoch") or state.get("current_epoch") or 1)


def epoch_snapshot_for_manifest(manifest: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    epoch_id = manifest_epoch_id(manifest, state)
    epoch = find_epoch(state, epoch_id)
    if epoch is not None:
        return epoch
    if manifest.get("input_hashes") is not None and manifest.get("config_sha256"):
        return {
            "evaluator": manifest.get("evaluator"),
            "input_hashes": manifest.get("input_hashes"),
            "config_sha256": manifest.get("config_sha256"),
        }
    return None


def incomparable_with_current(manifest: dict[str, Any], state: dict[str, Any], config: LabConfig) -> str | None:
    migrate_state(state)
    epoch_id = manifest_epoch_id(manifest, state)
    current_epoch = int(state.get("current_epoch") or 1)
    if epoch_id != current_epoch:
        return "incomparable_with_current: measurement contract changed"
    current = epoch_fingerprint(config, state)
    snapshot = {
        "config_sha256": manifest.get("config_sha256"),
        "input_hashes": manifest.get("input_hashes"),
        "evaluator": manifest.get("evaluator"),
    }
    epoch = find_epoch(state, epoch_id)
    if epoch is not None:
        for key in ("config_sha256", "input_hashes", "evaluator"):
            if snapshot.get(key) is None:
                snapshot[key] = epoch.get(key)
    for key in ("config_sha256", "input_hashes"):
        if snapshot.get(key) != current.get(key):
            return f"incomparable_with_current: {key} differs from the current contract"
    if list(snapshot.get("evaluator") or []) != list(current.get("evaluator") or []):
        return "incomparable_with_current: evaluator differs from the current contract"
    return None


def check_guard_thresholds(
    metrics: dict[str, Any],
    guard_thresholds: dict[str, dict[str, float]] | list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """Check explicit min_threshold and max_threshold bounds on guard metrics."""
    if not guard_thresholds or not metrics:
        return True, None

    normalized_guards: dict[str, dict[str, float]] = {}
    if isinstance(guard_thresholds, dict):
        normalized_guards = guard_thresholds
    elif isinstance(guard_thresholds, (list, tuple)):
        for item in guard_thresholds:
            if isinstance(item, dict) and "name" in item:
                name = item["name"]
                thresh = {}
                if "min_threshold" in item and item["min_threshold"] is not None:
                    thresh["min_threshold"] = float(item["min_threshold"])
                if "max_threshold" in item and item["max_threshold"] is not None:
                    thresh["max_threshold"] = float(item["max_threshold"])
                if thresh:
                    normalized_guards[name] = thresh

    for name, bounds in normalized_guards.items():
        if name not in metrics:
            continue
        val = metrics[name]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
            return False, f"guard {name} has invalid non-numeric value: {val!r}"
        val = float(val)
        min_t = bounds.get("min_threshold")
        if min_t is not None and val < min_t:
            return False, f"guard {name} below min_threshold ({val} < {min_t})"
        max_t = bounds.get("max_threshold")
        if max_t is not None and val > max_t:
            return False, f"guard {name} above max_threshold ({val} > {max_t})"

    return True, None
