"""Small, dependency-free runtime acceptance checks for the LJ module."""

from copy import deepcopy
import math

VERSION_KEYS = ("scene", "airspace", "risk_data", "risk_model", "planner_config")
VALID_STATUSES = {"feasible", "infeasible", "unknown"}
VALID_FRESHNESS = {"current_at_check", "stale", "unavailable"}


def _failure(code, message):
    return {"code": code, "message": message}


def _valid_versions(value):
    return (
        isinstance(value, dict)
        and all(
            isinstance(value.get(key), str) and bool(value[key].strip())
            for key in VERSION_KEYS
        )
    )


def _valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def validate_result(result, current_versions, max_elapsed_ms=5000, *, purpose="current"):
    """Validate a planner result without turning failures into success-shaped data."""
    failures = []
    if not isinstance(result, dict):
        return {"status": "fail", "failures": [_failure("invalid_result", "result is not an object")]}

    if purpose not in {"current", "history"}:
        failures.append(_failure("invalid_purpose", "purpose must be current or history"))

    status = result.get("status")
    if status not in VALID_STATUSES:
        failures.append(_failure("invalid_status", "status must be feasible, infeasible, or unknown"))

    versions = result.get("versions")
    if not _valid_versions(versions) or not _valid_versions(current_versions):
        failures.append(_failure("invalid_versions", "both results must contain five non-empty version strings"))
    elif purpose == "current" and any(versions[key] != current_versions[key] for key in VERSION_KEYS):
        failures.append(_failure("version_mismatch", "result is not bound to the current five-component snapshot"))

    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        failures.append(_failure("missing_reason", "every result needs an actionable reason"))

    freshness = result.get("freshness")
    if freshness is not None and freshness not in VALID_FRESHNESS:
        failures.append(_failure("invalid_freshness", "freshness must be current_at_check, stale, or unavailable"))
    elif freshness == "unavailable":
        failures.append(_failure(
            "release_unavailable",
            "the result has no available published release",
        ))
    elif freshness == "stale" and purpose == "current":
        failures.append(_failure(
            "stale_release",
            "a stale release cannot be accepted as the current recommendation",
        ))
    elif freshness is not None and freshness != "current_at_check" and purpose == "current":
        failures.append(_failure(
            "release_not_current",
            "the result is not from the current published release",
        ))

    if not _valid_number(max_elapsed_ms):
        failures.append(_failure("invalid_budget", "max_elapsed_ms must be a finite non-negative number"))

    if status == "feasible":
        metrics = result.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(_failure("missing_metrics", "feasible results require metrics"))
        else:
            for key in ("length_m", "time_s", "risk_proxy"):
                if not _valid_number(metrics.get(key)):
                    failures.append(_failure("invalid_metric", f"{key} must be a finite non-negative number"))
        if not isinstance(result.get("path"), list) or not result["path"]:
            failures.append(_failure("missing_path", "feasible results require a path"))
    elif result.get("metrics") not in (None, {}):
        failures.append(_failure("failure_has_metrics", "non-feasible results must not expose success metrics"))

    elapsed_ms = result.get("elapsed_ms")
    if elapsed_ms is not None and not _valid_number(elapsed_ms):
        failures.append(_failure("invalid_elapsed", "elapsed_ms must be a finite non-negative number"))
    elif _valid_number(elapsed_ms) and _valid_number(max_elapsed_ms) and elapsed_ms > max_elapsed_ms:
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
