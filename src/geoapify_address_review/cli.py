"""One-address command line interface, with an offline fixture mode."""

import argparse
import json
import math
import os
from pathlib import Path
import sys

from . import __version__
from .core import AddressReviewError, fetch_response, review_response, validate_input
from .render import render_text

MAX_FIXTURE_BYTES = 1_048_576
LOCAL_ERRORS = {
    "invalid_arguments", "invalid_input", "invalid_api_key", "missing_api_key", "fixture_error"
}


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AddressReviewError("invalid_arguments", message)


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def reject_json_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number")


def load_fixture(path: str) -> dict:
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_FIXTURE_BYTES + 1)
        if len(raw) > MAX_FIXTURE_BYTES:
            raise AddressReviewError("fixture_error", "Fixture exceeds the 1 MiB size limit.")
        return json.loads(raw.decode("utf-8"), parse_constant=reject_json_constant)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise AddressReviewError(
            "fixture_error", "Cannot read the fixture as UTF-8 JSON. Check its path and contents."
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = Parser(
        prog="address-review",
        description="Inspect Geoapify address candidates and explain review flags.",
        allow_abbrev=False,
    )
    parser.add_argument("address", metavar="ADDRESS", help="one free-form address")
    parser.add_argument("--country", metavar="CODE", help="optional two-letter country filter")
    parser.add_argument(
        "--timeout", type=positive_timeout, default=10.0, metavar="SECONDS",
        help="HTTP socket timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--fixture", metavar="PATH",
        help="read a saved JSON response without network access or an API key",
    )
    parser.add_argument(
        "--format", choices=("json", "text"), default="json",
        help="report format (default: json); errors always use JSON",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    try:
        args = parser.parse_args(argv)
        _, country = validate_input(args.address, args.country)
        if args.fixture is not None:
            response = load_fixture(args.fixture)
        else:
            response = fetch_response(
                args.address,
                os.environ.get("GEOAPIFY_API_KEY", ""),
                country=country,
                timeout=args.timeout,
            )
        report = review_response(args.address, response)
        report["source"] = "fixture" if args.fixture is not None else "live"
        report["country_filter"] = None if args.fixture is not None else country
        report["tool_version"] = __version__
    except AddressReviewError as error:
        details = {"code": error.code, "message": error.message}
        if error.http_status is not None:
            details["http_status"] = error.http_status
        print(json.dumps({"error": details}), file=sys.stderr)
        return 2 if error.code in LOCAL_ERRORS else 1
    if args.format == "text":
        # An ASCII-only terminal must still receive a complete readable report.
        encoding = sys.stdout.encoding or "utf-8"
        output = render_text(report).encode(encoding, errors="backslashreplace").decode(encoding)
        print(output)
    else:
        print(json.dumps(report, indent=2, allow_nan=False))
    return 0
