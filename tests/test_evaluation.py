"""The live-evaluation harness is tested without network access."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from geoapify_address_review.core import AddressReviewError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluation", ROOT / "scripts" / "evaluate.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)
SECRET = 'test-secret-"must-not-appear'


class EvaluationTests(unittest.TestCase):
    def run_main(self, argv, *, response=None, failure=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(evaluation.os.environ, {"GEOAPIFY_API_KEY": SECRET}, clear=True),
            patch.object(evaluation, "fetch_response", return_value=response, side_effect=failure) as fetch,
            patch.object(evaluation.time, "sleep") as sleep,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = evaluation.main(argv)
        return code, stdout.getvalue(), stderr.getvalue(), fetch, sleep

    def test_dry_run_never_uses_client_or_waits(self):
        code, output, errors, fetch, sleep = self.run_main([])
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["attempted_requests"], 0)
        self.assertEqual(report["planned_requests"], 10)
        self.assertTrue(all(item["outcome"] == "not_run" for item in report["observations"]))
        self.assertTrue(report["started_at"].endswith("Z"))
        self.assertTrue(report["completed_at"].endswith("Z"))
        fetch.assert_not_called()
        sleep.assert_not_called()

    def test_live_run_is_bounded_spaced_and_preserves_review_reports(self):
        code, output, errors, fetch, sleep = self.run_main(["--live"], response={"results": []})
        report = json.loads(output)
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(fetch.call_count, 10)
        self.assertEqual(sleep.call_count, 9)
        self.assertTrue(all(call.args == (1,) for call in sleep.call_args_list))
        self.assertEqual(report["attempted_requests"], 10)
        self.assertTrue(all(item["report"]["status"] == "no_result" for item in report["observations"]))
        self.assertEqual(report["observations"][7]["country"], "fr")
        self.assertEqual(fetch.call_args_list[7].kwargs["country"], "fr")
        self.assertNotIn(SECRET, output + errors)

    def test_first_client_failure_stops_without_retry_or_secret_leak(self):
        for error in (
            AddressReviewError("authentication_error", SECRET, 401),
            AddressReviewError("rate_limit", "https://example.test/?key=" + SECRET, 429),
            RuntimeError(SECRET),
        ):
            with self.subTest(error=type(error).__name__):
                code, output, errors, fetch, sleep = self.run_main(["--live"], failure=error)
                report = json.loads(output)
                self.assertEqual((code, errors), (1, ""))
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(report["status"], "stopped")
                self.assertEqual(report["observations"][0]["outcome"], "error")
                self.assertTrue(all(item["outcome"] == "skipped" for item in report["observations"][1:]))
                self.assertNotIn(SECRET, output)
                self.assertNotIn("example.test", output)

    def test_later_failure_keeps_completed_observations(self):
        responses = [{"results": []}, AddressReviewError("network_error", SECRET)]
        code, output, _, fetch, sleep = self.run_main(["--live"], failure=responses)
        report = json.loads(output)
        self.assertEqual(code, 1)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(report["observations"][0]["outcome"], "completed")
        self.assertEqual(report["observations"][1]["outcome"], "error")
        self.assertEqual(report["observations"][2]["outcome"], "skipped")

    def test_upstream_echo_of_secret_is_redacted_in_printed_report(self):
        response = {"results": [{"formatted": "echo " + SECRET}]}
        code, output, _, _, _ = self.run_main(["--live"], response=response)
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report["observations"][0]["report"]["candidates"][0]["formatted"], "echo [REDACTED]")
        self.assertNotIn(SECRET, output)

    def test_response_unicode_remains_safe_to_print_as_json(self):
        response = {"results": [{"formatted": "Upstream text: \ud800"}]}
        code, output, _, _, _ = self.run_main(["--live"], response=response)
        self.assertEqual(code, 0)
        self.assertNotIn("\ud800", output)
        output.encode("ascii")
        report = json.loads(output)
        self.assertEqual(report["observations"][0]["report"]["candidates"][0]["formatted"], "Upstream text: \ud800")

    def test_entire_file_is_validated_before_any_call(self):
        cases = evaluation.load_cases(evaluation.CASE_FILE)
        invalid_cases = [
            cases + [{**cases[0], "id": "eleventh"}],
            cases[:-1] + [{**cases[-1], "input": ""}],
            cases[:-1] + [{**cases[-1], "id": cases[0]["id"]}],
        ]
        for invalid in invalid_cases:
            with self.subTest(case_count=len(invalid)), tempfile.TemporaryDirectory() as directory:
                case_file = Path(directory) / "cases.json"
                case_file.write_text(json.dumps({"cases": invalid}), encoding="utf-8")
                with patch.object(evaluation, "CASE_FILE", case_file):
                    code, output, errors, fetch, sleep = self.run_main(["--live"])
                self.assertEqual((code, output), (2, ""))
                self.assertEqual(json.loads(errors)["error"]["code"], "invalid_setup")
                fetch.assert_not_called()
                sleep.assert_not_called()

    def test_live_requires_key_but_dry_run_does_not(self):
        for argv, expected in (([], 0), (["--live"], 2)):
            with (
                patch.dict(evaluation.os.environ, {}, clear=True),
                patch.object(evaluation, "fetch_response") as fetch,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(evaluation.main(argv), expected)
                fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
