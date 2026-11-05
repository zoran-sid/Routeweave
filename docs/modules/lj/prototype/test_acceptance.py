import unittest

from acceptance import needs_revalidation, publish_snapshot, validate_result, verify_recovery


VERSIONS = {
    "scene": "scene-v1",
    "airspace": "airspace-v1",
    "risk_data": "risk-v1",
    "risk_model": "model-v1",
    "planner_config": "config-v1",
}


def result(status="feasible", **extra):
    base = {
        "status": status,
        "reason": "synthetic_acceptance",
        "versions": dict(VERSIONS),
        "path": [[0, 0, 20], [10, 0, 20]],
        "metrics": {"length_m": 10, "time_s": 1, "risk_proxy": 0.1},
        "elapsed_ms": 20,
    }
    if status != "feasible":
        base["path"] = None
        base["metrics"] = None
    base.update(extra)
    return base


class AcceptanceTests(unittest.TestCase):
    def test_feasible_result(self):
        self.assertEqual(validate_result(result(), VERSIONS)["status"], "pass")

    def test_infeasible_result_has_no_success_metrics(self):
        self.assertEqual(validate_result(result("infeasible"), VERSIONS)["status"], "pass")

    def test_unknown_requires_reason(self):
        checked = validate_result(result("unknown", reason=""), VERSIONS)
        self.assertEqual(checked["status"], "fail")
        self.assertEqual(checked["failures"][0]["code"], "missing_reason")

    def test_version_mismatch(self):
        checked = validate_result(result(versions={**VERSIONS, "airspace": "airspace-v2"}), VERSIONS)
        self.assertEqual(checked["status"], "fail")
        self.assertIn("version_mismatch", [item["code"] for item in checked["failures"]])

    def test_missing_versions_fail_even_when_both_are_empty(self):
        checked = validate_result(result(versions={}), {})
        self.assertEqual(checked["status"], "fail")
        self.assertIn("invalid_versions", [item["code"] for item in checked["failures"]])

    def test_missing_or_invalid_version_fields_fail(self):
        for versions, current in (
            ({key: value for key, value in VERSIONS.items() if key != "scene"}, VERSIONS),
            (VERSIONS, {key: value for key, value in VERSIONS.items() if key != "scene"}),
            ({**VERSIONS, "scene": ""}, VERSIONS),
            ({**VERSIONS, "scene": True}, VERSIONS),
        ):
            with self.subTest(versions=versions, current=current):
                self.assertEqual(validate_result(result(versions=versions), current)["status"], "fail")

    def test_stale_release_is_not_current_recommendation(self):
        checked = validate_result(result(freshness="stale"), VERSIONS)
        self.assertEqual(checked["status"], "fail")
        self.assertIn("stale_release", [item["code"] for item in checked["failures"]])

    def test_stale_release_can_be_viewed_as_history(self):
        old_versions = {**VERSIONS, "airspace": "airspace-v0"}
        checked = validate_result(
            result(versions=old_versions, freshness="stale"),
            VERSIONS,
            purpose="history",
        )
        self.assertEqual(checked["status"], "pass")

    def test_unavailable_release_fails_current_and_history(self):
        for purpose in ("current", "history"):
            with self.subTest(purpose=purpose):
                self.assertEqual(
                    validate_result(result(freshness="unavailable"), VERSIONS, purpose=purpose)["status"],
                    "fail",
                )

    def test_non_finite_and_boolean_values_fail(self):
        for key in ("length_m", "time_s", "risk_proxy"):
            for value in (float("nan"), float("inf"), float("-inf"), True, -1):
                with self.subTest(key=key, value=value):
                    metrics = {**result()["metrics"], key: value}
                    self.assertEqual(validate_result(result(metrics=metrics), VERSIONS)["status"], "fail")
        for value in (float("nan"), float("inf"), float("-inf"), True, -1):
            with self.subTest(elapsed_ms=value):
                self.assertEqual(validate_result(result(elapsed_ms=value), VERSIONS)["status"], "fail")

    def test_elapsed_budget_is_applied_to_finite_values(self):
        checked = validate_result(result(elapsed_ms=5001), VERSIONS, max_elapsed_ms=5000)
        self.assertEqual(checked["status"], "fail")
        self.assertIn("budget_exceeded", [item["code"] for item in checked["failures"]])

    def test_failed_publish_keeps_previous_snapshot(self):
        old = {"version": "manifest-v1", "digest": "old"}
        candidate = {"version": "manifest-v2", "digest": "new"}
        published = publish_snapshot({"active": old}, candidate, False)
        self.assertEqual(published["outcome"], "rejected")
        self.assertEqual(published["active"], old)

    def test_affected_update_requires_revalidation(self):
        changed = {**VERSIONS, "risk_data": "risk-v2"}
        self.assertTrue(needs_revalidation(result(), changed, {"risk_data"}))
        self.assertFalse(needs_revalidation(result(), changed, {"airspace"}))

    def test_budget_overrun(self):
        checked = validate_result(result(elapsed_ms=6000), VERSIONS)
        self.assertEqual(checked["status"], "fail")
        self.assertIn("budget_exceeded", [item["code"] for item in checked["failures"]])

    def test_recovery_digest_mismatch(self):
        self.assertFalse(verify_recovery({"version": "v2", "digest": "wrong"}, "expected"))
        self.assertTrue(verify_recovery({"version": "v2", "digest": "expected"}, "expected"))


if __name__ == "__main__":
    unittest.main()
