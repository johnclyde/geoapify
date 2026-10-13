"""Offline behavior and command-line contract checks.

All addresses and API responses below are synthetic. No test makes a live request.
"""

import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from geoapify_address_review import core


ROOT = Path(__file__).resolve().parents[1]
ADDRESS = "10 Example Street, Example City"
API_KEY = "test-secret-do-not-expose"


def precise_result():
    return {
        "formatted": ADDRESS,
        "housenumber": "10",
        "street": "Example Street",
        "city": "Example City",
        "country_code": "us",
        "result_type": "building",
        "lon": -122.4194,
        "lat": 37.7749,
        "rank": {"confidence": 1.0, "match_type": "full_match"},
        "datasource": {"sourcename": "synthetic test fixture"},
    }


def fake_response(body, status=200):
    response = MagicMock()
    response.__enter__.return_value = response
    response.getcode.return_value = status
    response.read.return_value = body
    return response


class ReviewTests(unittest.TestCase):
    def test_precise_single_result_has_clear_report(self):
        for result_type in ("building", "amenity"):
            with self.subTest(result_type=result_type):
                result = precise_result()
                result["result_type"] = result_type
                report = core.review_response(ADDRESS, {"results": [result]})
                self.assertEqual(report["input"], ADDRESS)
                self.assertEqual(report["status"], "candidate_found")
                self.assertEqual(report["candidate_count"], 1)
                self.assertEqual(len(report["candidates"]), 1)
                self.assertTrue(report["notice"])
                self.assertIsInstance(report["reasons"], list)
                self.assertEqual(report["candidates"][0]["formatted"], ADDRESS)

    def test_uncertainty_never_becomes_a_confirmed_candidate(self):
        cases = {}
        for name, update in (
            ("street-level", {"result_type": "street"}),
            ("missing house number", {"housenumber": None}),
            ("missing street", {"street": None}),
            ("missing longitude", {"lon": None}),
            ("nonfinite latitude", {"lat": float("inf")}),
            ("out-of-range longitude", {"lon": 181}),
            ("boolean coordinate", {"lat": True}),
            ("low confidence", {"rank": {"confidence": 0.99, "match_type": "full_match"}}),
            ("boolean confidence", {"rank": {"confidence": True, "match_type": "full_match"}}),
            ("partial match", {"rank": {"confidence": 1, "match_type": "match_by_street"}}),
            ("missing rank", {"rank": None}),
        ):
            candidate = precise_result()
            candidate.update(update)
            cases[name] = [candidate]
        cases["multiple precise candidates"] = [precise_result(), precise_result()]
        for name, results in cases.items():
            with self.subTest(case=name):
                report = core.review_response(ADDRESS, {"results": results})
                self.assertEqual(report["status"], "needs_review")
                self.assertEqual(report["candidate_count"], len(results))
                self.assertTrue(report["reasons"], "The caller needs an explanation for review.")
                # Output must remain usable by strict JSON consumers even if an
                # upstream number was nonfinite.
                json.dumps(report, allow_nan=False)

    def test_empty_results_and_broken_response_shapes_are_distinct(self):
        report = core.review_response(ADDRESS, {"results": []})
        self.assertEqual(report["status"], "no_result")
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["candidates"], [])
        for payload in (None, [], {}, {"results": None}, {"results": {}}, {"results": [None]}):
            with self.subTest(payload=payload):
                with self.assertRaises(core.AddressReviewError) as caught:
                    core.review_response(ADDRESS, payload)
                self.assertEqual(caught.exception.code, "invalid_response")


class InputTests(unittest.TestCase):
    def test_input_normalization_and_rejection(self):
        self.assertEqual(core.validate_input("  " + ADDRESS + "  ", "US"), (ADDRESS, "us"))
        self.assertEqual(core.validate_input("1 Rue de l’École"), ("1 Rue de l’École", None))
        for address, country in (("", None), (" \t ", None), (None, None), (42, None), ("\ud800", None), (ADDRESS, "USA"), (ADDRESS, "1a")):
            with self.subTest(address=address, country=country):
                with self.assertRaises(core.AddressReviewError) as caught:
                    core.validate_input(address, country)
                self.assertEqual(caught.exception.code, "invalid_input")


class ClientTests(unittest.TestCase):
    def test_request_uses_header_auth_and_explicit_search_parameters(self):
        payload = {"results": [precise_result()]}
        with patch.object(core, "build_opener") as build_opener:
            opener = build_opener.return_value
            opener.open.return_value = fake_response(json.dumps(payload).encode("utf-8"))
            returned = core.fetch_response(ADDRESS, API_KEY, country="us", timeout=3.5)
        self.assertEqual(returned, payload)
        request = opener.open.call_args.args[0]
        parsed = urlsplit(request.full_url)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "api.geoapify.com")
        self.assertEqual(params["text"], [ADDRESS])
        self.assertEqual(params["format"], ["json"])
        self.assertEqual(params["limit"], ["3"])
        self.assertEqual(params["filter"], ["countrycode:us"])
        self.assertNotIn(API_KEY, request.full_url)
        self.assertNotIn("apiKey", params)
        self.assertEqual(dict((key.lower(), value) for key, value in request.header_items())["x-api-key"], API_KEY)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 3.5)
        # Authentication must not follow a redirect to an unrelated host.
        handlers = build_opener.call_args.args
        redirect_handlers = [handler for handler in handlers if hasattr(handler, "redirect_request")]
        self.assertTrue(redirect_handlers)
        self.assertIsNone(redirect_handlers[0].redirect_request(request, None, 302, "Moved", {}, "https://example.org/"))

    def test_failures_have_safe_actionable_errors(self):
        cases = (
            (HTTPError("https://api.geoapify.com/v1/geocode/search", 429, API_KEY, {}, io.BytesIO(API_KEY.encode())), "rate_limit", 429),
            (HTTPError("https://api.geoapify.com/v1/geocode/search", 401, API_KEY, {}, io.BytesIO(API_KEY.encode())), "authentication_error", 401),
            (HTTPError("https://api.geoapify.com/v1/geocode/search", 302, API_KEY, {}, io.BytesIO(API_KEY.encode())), "http_error", 302),
            (URLError(API_KEY), "network_error", None),
            (TimeoutError(API_KEY), "network_error", None),
        )
        for failure, code, status in cases:
            with self.subTest(code=code, status=status):
                with patch.object(core, "build_opener") as build_opener:
                    build_opener.return_value.open.side_effect = failure
                    with self.assertRaises(core.AddressReviewError) as caught:
                        core.fetch_response(ADDRESS, API_KEY)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.http_status, status)
                self.assertNotIn(API_KEY, caught.exception.message)
                self.assertNotIn(API_KEY, str(caught.exception))
        with patch.object(core, "build_opener") as build_opener:
            build_opener.return_value.open.return_value = fake_response(b"not JSON " + API_KEY.encode())
            with self.assertRaises(core.AddressReviewError) as caught:
                core.fetch_response(ADDRESS, API_KEY)
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertNotIn(API_KEY, caught.exception.message)


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        environment = os.environ.copy()
        environment.pop("GEOAPIFY_API_KEY", None)
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "geoapify_address_review", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_fixture_mode_runs_without_credentials_and_reports_all_outcomes(self):
        coarse = copy.deepcopy(precise_result())
        coarse["result_type"] = "street"
        surrogate_text = precise_result()
        surrogate_text["formatted"] = "Upstream text with a lone surrogate: \ud800"
        for results, expected in (([precise_result()], "candidate_found"), ([coarse], "needs_review"), ([], "no_result"), ([surrogate_text], "candidate_found")):
            with self.subTest(status=expected), tempfile.TemporaryDirectory() as directory:
                fixture = Path(directory) / "response.json"
                fixture.write_text(json.dumps({"results": results}), encoding="utf-8")
                completed = self.run_cli(ADDRESS, "--fixture", str(fixture))
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")
                report = json.loads(completed.stdout)
                self.assertEqual(report["status"], expected)
                self.assertEqual(report["input"], ADDRESS)

    def test_cli_errors_are_json_on_stderr_with_defined_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            broken_json = Path(directory) / "broken.json"
            broken_json.write_text("{", encoding="utf-8")
            broken_schema = Path(directory) / "schema.json"
            broken_schema.write_text('{"results": null}', encoding="utf-8")
            nonfinite_json = Path(directory) / "nonfinite.json"
            nonfinite_json.write_text('{"results": [{"lat": NaN}]}', encoding="utf-8")
            cases = (
                ((ADDRESS,), 2, "missing_api_key"),
                ((ADDRESS, "--fixture", str(Path(directory) / "missing.json")), 2, "fixture_error"),
                ((ADDRESS, "--fixture", str(broken_json)), 2, "fixture_error"),
                ((ADDRESS, "--fixture", str(nonfinite_json)), 2, "fixture_error"),
                ((ADDRESS, "--fixture", str(broken_schema)), 1, "invalid_response"),
                ((ADDRESS, "--unknown-option"), 2, "invalid_arguments"),
            )
            for arguments, exit_status, error_code in cases:
                with self.subTest(error=error_code, arguments=arguments):
                    completed = self.run_cli(*arguments)
                    self.assertEqual(completed.returncode, exit_status, completed.stderr)
                    self.assertEqual(completed.stdout, "")
                    error = json.loads(completed.stderr)["error"]
                    self.assertEqual(error["code"], error_code)
                    self.assertTrue(error["message"])
                    self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
