"""Behavior checks for candidate selection, evidence, and readable output."""

import contextlib
import copy
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from geoapify_address_review import cli, core
from test_address_review import ADDRESS, API_KEY, ROOT, precise_result


class CandidateSelectionTests(unittest.TestCase):
    def test_exact_duplicates_preserve_rows_but_count_once(self):
        candidate = precise_result()
        report = core.review_response(
            ADDRESS, {"results": [candidate, copy.deepcopy(candidate), copy.deepcopy(candidate)]}
        )
        self.assertEqual(report["status"], "candidate_found")
        self.assertEqual(report["candidate_count"], 3)
        self.assertEqual(report["distinct_candidate_count"], 1)
        self.assertEqual(report["selected_candidate"], 1)
        self.assertEqual([item["duplicate_of"] for item in report["candidates"]], [None, 1, 1])
        self.assertEqual([item["assessment"] for item in report["candidates"]], ["meets_rules"] * 3)

    def test_one_strong_candidate_survives_only_explicitly_coarse_alternatives(self):
        for result_type in ("street", "suburb", "district", "city", "county", "state", "postcode", "country"):
            coarse = precise_result()
            coarse["result_type"] = result_type
            for rows in itertools.permutations([precise_result(), coarse]):
                with self.subTest(result_type=result_type, first=rows[0]["result_type"]):
                    report = core.review_response(ADDRESS, {"results": list(rows)})
                    expected_index = next(index for index, row in enumerate(rows, 1) if row["result_type"] == "building")
                    self.assertEqual(report["status"], "candidate_found")
                    self.assertEqual(report["distinct_candidate_count"], 2)
                    self.assertEqual(report["selected_candidate"], expected_index)
                    strong = report["candidates"][expected_index - 1]
                    weak = report["candidates"][2 - expected_index]
                    self.assertEqual(strong["assessment"], "meets_rules")
                    self.assertEqual(weak["assessment"], "needs_review")
                    self.assertIn("result_type_not_precise", weak["reason_codes"])
                    self.assertTrue(weak["reasons"])

    def test_precise_and_unknown_alternatives_remain_ambiguous_in_any_order(self):
        alternatives = []
        second_strong = precise_result()
        second_strong.update({"housenumber": "12", "formatted": "12 Example Street, Example City"})
        alternatives.append(("two strong candidates", second_strong))
        for result_type in ("building", "amenity", "unknown", None):
            weaker = precise_result()
            weaker["result_type"] = result_type
            weaker["rank"]["confidence"] = 0.4
            alternatives.append((f"weak {result_type} alternative", weaker))
        for label, alternative in alternatives:
            for rows in itertools.permutations([precise_result(), alternative]):
                with self.subTest(case=label, first=rows[0]["formatted"]):
                    report = core.review_response(ADDRESS, {"results": list(rows)})
                    self.assertEqual(report["status"], "needs_review")
                    self.assertEqual(report["distinct_candidate_count"], 2)
                    self.assertIsNone(report["selected_candidate"])
                    self.assertTrue(report["reasons"])

    def test_duplicate_detection_preserves_differences_in_raw_evidence(self):
        changed_metadata = precise_result()
        changed_metadata["provider_record_id"] = "a separate source record"
        boolean_confidence = precise_result()
        boolean_confidence["rank"]["confidence"] = True
        for alternate in (changed_metadata, boolean_confidence):
            with self.subTest(alternate=alternate):
                report = core.review_response(ADDRESS, {"results": [precise_result(), alternate]})
                self.assertEqual(report["status"], "needs_review")
                self.assertEqual(report["distinct_candidate_count"], 2)
                self.assertEqual([item["duplicate_of"] for item in report["candidates"]], [None, None])
                self.assertIsNone(report["selected_candidate"])

    def test_present_component_confidence_can_veto_overall_confidence(self):
        fields = ("confidence_city_level", "confidence_street_level", "confidence_building_level")
        for field in fields:
            for value, reason_code in ((0.8, field + "_below_one"), (0, field + "_below_one"), (None, "invalid_rank"), (True, "invalid_rank"), ("1", "invalid_rank"), (1.1, "invalid_rank")):
                with self.subTest(field=field, value=value):
                    candidate = precise_result()
                    candidate["rank"][field] = value
                    report = core.review_response(ADDRESS, {"results": [candidate]})
                    self.assertEqual(report["status"], "needs_review")
                    self.assertIsNone(report["selected_candidate"])
                    assessed = report["candidates"][0]
                    self.assertEqual(assessed["assessment"], "needs_review")
                    self.assertIn(reason_code, assessed["reason_codes"])
                    self.assertTrue(assessed["reasons"])
        candidate = precise_result()
        candidate["rank"].update(dict.fromkeys(fields, 1))
        self.assertEqual(core.review_response(ADDRESS, {"results": [candidate]})["status"], "candidate_found")


class ImprovedCLITests(unittest.TestCase):
    def test_empty_fixture_path_never_falls_back_to_a_live_request(self):
        errors = io.StringIO()
        with patch.object(cli, "fetch_response") as fetch, contextlib.redirect_stderr(errors):
            status = cli.main([ADDRESS, "--fixture", ""])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(errors.getvalue())["error"]["code"], "fixture_error")
        fetch.assert_not_called()

    def run_fixture(self, results, *options):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "response.json"
            fixture.write_text(json.dumps({"results": results}), encoding="utf-8")
            environment = os.environ.copy()
            environment.pop("GEOAPIFY_API_KEY", None)
            environment["PYTHONPATH"] = str(ROOT / "src")
            return subprocess.run(
                [sys.executable, "-m", "geoapify_address_review", ADDRESS, "--fixture", str(fixture), *options],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10, check=False,
            )

    def test_fixture_reports_provenance_and_readable_selection(self):
        coarse = precise_result()
        coarse["result_type"] = "street"
        completed = self.run_fixture([coarse, precise_result()], "--country", "US")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["source"], "fixture")
        self.assertIsNone(report["country_filter"], "A saved fixture has not applied the requested filter.")
        self.assertEqual(report["selected_candidate"], 2)
        completed = self.run_fixture([coarse, precise_result()], "--format", "text")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        self.assertIn(ADDRESS, completed.stdout)
        self.assertIn("candidate_found", completed.stdout)
        self.assertIn("fixture", completed.stdout.lower())
        self.assertIn("full_match", completed.stdout)

    def test_live_provenance_reflects_normalized_country(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"GEOAPIFY_API_KEY": API_KEY}), patch.object(cli, "fetch_response", return_value={"results": [precise_result()]}) as fetch, contextlib.redirect_stdout(output):
            status = cli.main([ADDRESS, "--country", "US"])
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["source"], "live")
        self.assertEqual(report["country_filter"], "us")
        self.assertEqual(fetch.call_args.kwargs["country"], "us")
        self.assertNotIn(API_KEY, output.getvalue())

    def test_text_output_escapes_untrusted_controls_and_preserves_json_errors(self):
        candidate = precise_result()
        candidate["formatted"] = "Display\nFORGED\r\x1b[31m\t\x7f\u202e\ud800"
        completed = self.run_fixture([candidate], "--format", "text")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        for unsafe in ("\nFORGED", "\r", "\x1b", "\t", "\x7f", "\u202e", "\ud800"):
            self.assertNotIn(unsafe, completed.stdout)
        self.assertIn("Display", completed.stdout)
        self.assertIn("FORGED", completed.stdout)
        # Selecting readable success output does not change machine-readable failures.
        errors = io.StringIO()
        output = io.StringIO()
        with patch.dict(os.environ, {"GEOAPIFY_API_KEY": ""}), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = cli.main([ADDRESS, "--format", "text"])
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(errors.getvalue())["error"]["code"], "missing_api_key")


if __name__ == "__main__":
    unittest.main()
