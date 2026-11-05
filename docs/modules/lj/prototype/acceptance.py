"""Small, dependency-free runtime acceptance checks for the LJ module."""

from copy import deepcopy

VERSION_KEYS = ("scene", "airspace", "risk_data", "risk_model", "planner_config")
VALID_STATUSES = {"feasible", "infeasible", "unknown"}


def _failure(code, message):
    return {"code": code, "message": message}


def validate_result(result, current_versions, max_elapsed_ms=5000):
    """Validate a planner result without turning failures into success-shaped data."""
    failures = []
    if not isinstance(result, dict):
        return {"status": "fail", "failures": [_failure("invalid_result", "result is not an object")]}

    status = result.get("status")
    if status not in VALID_STATUSES:
        failures.append(_failure("invalid_status", "status must be feasible, infeasible, or unknown"))

    versions = result.get("versions")
    if not isinstance(versions, dict) or any(
        versions.get(key) != current_versions.get(key) for key in VERSION_KEYS
    ):
        failures.append(_failure("version_mismatch", "result is not bound to the current five-component snapshot"))

    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        failures.append(_failure("missing_reason", "every result needs an actionable reason"))

    if status == "feasible":
        metrics = result.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(_failure("missing_metrics", "feasible results require metrics"))
        else:
            for key in ("length_m", "time_s", "risk_proxy"):
                if not isinstance(metrics.get(key), (int, float)) or metrics[key] < 0:
                    failures.append(_failure("invalid_metric", f"{key} must be a non-negative number"))
        if not isinstance(result.get("path"), list) or not result["path"]:
            failures.append(_failure("missing_path", "feasible results require a path"))
    elif result.get("metrics") not in (None, {}):
        failures.append(_failure("failure_has_metrics", "non-feasible results must not expose success metrics"))

    elapsed_ms = result.get("elapsed_ms")
    if elapsed_ms is not None and (
        not isinstance(elapsed_ms, (int, float)) or elapsed_ms < 0 or elapsed_ms > max_elapsed_ms
    ):
        failures.append(_failure("budget_exceeded", "result exceeded the configured execution budget"))

    return {"status": "pass" if not failures else "fail", "failures": failures}


def needs_revalidation(old_result, new_versions, affected_components):
    """Return whether an old result is stale after a published component changes."""
    if not isinstance(old_result, dict) or old_result.get("status") != "feasible":
        return False
    old_versions = old_result.get("versions", {})
    changed = {
        key for key in VERSION_KEYS if old_versions.get(key) != new_versions.get(key)
    }
    return bool(changed.intersection(set(affected_components)))


def publish_snapshot(state, candidate, validation_passed):
    """Apply a publish only after validation; failed writes preserve the old snapshot."""
    before = deepcopy(state)
    if not validation_passed:
        return {
            "active": before["active"],
            "outcome": "rejected",
            "audit": {"result": "failure", "candidate": candidate.get("version")},
        }
    return {
        "active": deepcopy(candidate),
        "outcome": "published",
        "audit": {"result": "success", "candidate": candidate.get("version")},
    }


def verify_recovery(restored, expected_digest):
    """Return false instead of replaying a recovery object with a wrong digest."""
    return restored.get("digest") == expected_digest and restored.get("version") is not None
