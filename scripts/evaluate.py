"""Bounded observation run for the ten public-address cases in this repository."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time

from geoapify_address_review import __version__
from geoapify_address_review.core import (
    AddressReviewError, fetch_response, review_response, validate_input,
)


CASE_FILE = Path(__file__).resolve().parents[1] / "examples" / "live-cases.json"
MAX_CASES = 10
REPORT_VERSION = "1"
SAFE_ERROR_CODES = {
    "authentication_error", "rate_limit", "http_error", "network_error",
    "invalid_response", "invalid_input", "missing_api_key", "invalid_api_key",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_cases(path: Path) -> list[dict]:
    """Validate the entire fixed case file before any request is permitted."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(65_537)
        if len(raw) > 65_536:
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        cases = payload["cases"]
        if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
            raise ValueError
        seen = set()
        clean = []
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError
            case_id, scenario = case["id"], case["scenario"]
            if (
                not isinstance(case_id, str)
                or not re.fullmatch(r"[a-z0-9_-]{1,64}", case_id)
                or case_id in seen
                or not isinstance(scenario, str)
                or not 1 <= len(scenario.strip()) <= 240
            ):
                raise ValueError
            scenario.encode("utf-8")
            address, country = validate_input(case["input"], case.get("country"))
            seen.add(case_id)
            clean.append({
                "id": case_id, "scenario": scenario.strip(),
                "input": address, "country": country,
            })
        return clean
    except (OSError, ValueError, KeyError, TypeError, RecursionError, AddressReviewError):
        raise ValueError(
            "The case file must contain 1 to 10 valid, uniquely named observation cases."
        ) from None


def require_key() -> str:
    key = os.environ.get("GEOAPIFY_API_KEY", "").strip()
    if not key:
        raise ValueError("Set GEOAPIFY_API_KEY before using --live.")
    if len(key) > 1024 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("GEOAPIFY_API_KEY has an invalid format.")
    return key


def evaluate(cases: list[dict], *, api_key: str | None = None) -> dict:
    """Run validated cases, or return a plan when api_key is absent."""
    if not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("Evaluation is limited to 1 to 10 cases.")
    report = {
        "report_version": REPORT_VERSION,
        "tool_version": __version__,
        "mode": "live" if api_key is not None else "dry_run",
        "started_at": utc_now(),
        "status": "planned" if api_key is None else "completed",
        "planned_requests": len(cases),
        "attempted_requests": 0,
        "observations": [{**case, "outcome": "not_run"} for case in cases],
        "notice": "Observation scenarios, not accuracy ground truth or deliverability checks.",
    }
    if api_key is not None:
        for index, observation in enumerate(report["observations"]):
            if index:
                time.sleep(1)
            observation["started_at"] = utc_now()
            report["attempted_requests"] += 1
            try:
                response = fetch_response(
                    observation["input"], api_key,
                    country=observation["country"], timeout=10.0,
                )
                observation["report"] = review_response(observation["input"], response)
                observation["outcome"] = "completed"
            except Exception as error:
                # Never copy exception messages, request URLs, or remote bodies.
                details = {
                    "code": "unexpected_client_error",
                    "message": "Client evaluation failed; stopped without retrying.",
                }
                if isinstance(error, AddressReviewError):
                    details["code"] = (
                        error.code if error.code in SAFE_ERROR_CODES else "client_error"
                    )
                    if type(error.http_status) is int and 100 <= error.http_status <= 599:
                        details["http_status"] = error.http_status
                observation["outcome"] = "error"
                observation["error"] = details
                report["status"] = "stopped"
            observation["completed_at"] = utc_now()
            if report["status"] == "stopped":
                for pending in report["observations"][index + 1:]:
                    pending["outcome"] = "skipped"
                break
    report["completed_at"] = utc_now()
    return report


def redact_secret(value, secret: str | None):
    """Protect against an upstream string echoing the credential into a report."""
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [redact_secret(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: redact_secret(item, secret) for key, item in value.items()}
    return value


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("Unrecognized arguments. Use --help for the supported options.")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--live", action="store_true",
        help="make at most ten real API calls; requires GEOAPIFY_API_KEY",
    )
    try:
        args = parser.parse_args(argv)
        cases = load_cases(CASE_FILE)
        key = require_key() if args.live else None
    except ValueError as error:
        print(json.dumps({"error": {"code": "invalid_setup", "message": str(error)}}), file=sys.stderr)
        return 2
    report = evaluate(cases, api_key=key)
    print(json.dumps(redact_secret(report, key), ensure_ascii=True, indent=2, allow_nan=False))
    return 1 if report["status"] == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
