"""Small Geoapify client and transparent, conservative address review rules."""

from __future__ import annotations

import json
import math
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__


API_URL = "https://api.geoapify.com/v1/geocode/search"
MAX_RESPONSE_BYTES = 1_048_576
NOTICE = (
    "This is a geocoding review aid, not postal deliverability verification. "
    "Confidence is an API score, not a probability. A full_match does not prove "
    "that an address exists or accepts mail. Review the candidate before use."
)
COMPONENT_FIELDS = (
    "name", "housenumber", "street", "postcode", "suburb", "district",
    "city", "county", "state", "state_code", "country", "country_code",
    "address_line1", "address_line2",
)
RANK_SCORE_FIELDS = (
    "confidence", "confidence_city_level", "confidence_street_level",
    "confidence_building_level", "importance", "popularity",
)
DATASOURCE_FIELDS = ("sourcename", "attribution", "license", "url")
COARSE_RESULT_TYPES = frozenset(
    ("street", "suburb", "district", "city", "county", "state", "postcode", "country")
)


class AddressReviewError(Exception):
    """A safe error suitable for JSON output, with no upstream body or URL."""

    def __init__(
        self, code: str, message: str, http_status: int | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def validate_input(
    address: str, country: str | None = None
) -> tuple[str, str | None]:
    """Normalize local input without making a request."""
    if not isinstance(address, str) or not address.strip():
        raise AddressReviewError("invalid_input", "Provide a nonempty address.")
    address = address.strip()
    try:
        address.encode("utf-8")
    except UnicodeEncodeError:
        raise AddressReviewError("invalid_input", "The address must contain valid Unicode text.") from None
    if len(address) > 1024:
        raise AddressReviewError(
            "invalid_input", "The address must contain at most 1024 characters."
        )
    if country is not None:
        if not isinstance(country, str):
            raise AddressReviewError(
                "invalid_input", "Country must be a two-letter country code."
            )
        country = country.strip()
        if len(country) != 2 or any(
            not ("a" <= c <= "z" or "A" <= c <= "Z") for c in country
        ):
            raise AddressReviewError(
                "invalid_input", "Country must be a two-letter country code."
            )
        country = country.lower()
    return address, country


class _NoRedirect(HTTPRedirectHandler):
    """Never forward an authenticated request to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_error(status: int) -> AddressReviewError:
    if status in (401, 403):
        return AddressReviewError(
            "authentication_error", "Geoapify rejected the API credentials.", status
        )
    if status == 429:
        return AddressReviewError(
            "rate_limit", "Geoapify reported a rate limit or exhausted quota.", status
        )
    return AddressReviewError(
        "http_error", "Geoapify returned an unsuccessful HTTP response.", status
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number")


def _results(payload: dict) -> list[dict]:
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("results"), list)
        or any(not isinstance(item, dict) for item in payload["results"])
    ):
        raise AddressReviewError(
            "invalid_response", "Expected a JSON object with a results array of objects."
        )
    return payload["results"]


def fetch_response(
    address: str,
    api_key: str,
    *,
    country: str | None = None,
    timeout: float = 10.0,
) -> dict:
    """Fetch at most three candidates once; errors omit remote bodies and secrets."""
    address, country = validate_input(address, country)
    if not isinstance(api_key, str) or not api_key.strip():
        raise AddressReviewError(
            "missing_api_key", "Set GEOAPIFY_API_KEY before making a live request."
        )
    api_key = api_key.strip()
    if len(api_key) > 1024 or any(not (33 <= ord(c) <= 126) for c in api_key):
        raise AddressReviewError("invalid_api_key", "The API key has an invalid format.")
    if not _finite_number(timeout) or timeout <= 0:
        raise AddressReviewError("invalid_input", "Timeout must be a finite positive number.")

    params = {
        "text": address,
        "format": "json",
        "limit": "3",
        "bias": "countrycode:none",
    }
    if country:
        params["filter"] = f"countrycode:{country}"
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": f"geoapify-address-review/{__version__}",
        },
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            status = response.getcode()
            if status != 200:
                raise _http_error(status)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        raise _http_error(status) from None
    except (URLError, OSError, HTTPException, ValueError, OverflowError):
        raise AddressReviewError(
            "network_error", "The Geoapify request could not be completed."
        ) from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AddressReviewError("invalid_response", "The API response exceeded 1 MiB.")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise AddressReviewError("invalid_response", "The API response was not valid JSON.") from None
    _results(payload)
    return payload


def _finite_number(value: object) -> bool:
    # bool is an int subclass, but true must not qualify as confidence 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _candidate(result: dict) -> dict:
    components = {
        key: text for key in COMPONENT_FIELDS
        if (text := _text(result.get(key))) is not None
    }
    lat, lon = result.get("lat"), result.get("lon")
    coordinates = None
    if (
        _finite_number(lat) and -90 <= lat <= 90
        and _finite_number(lon) and -180 <= lon <= 180
    ):
        coordinates = {"lat": lat, "lon": lon}

    raw_rank = result.get("rank")
    rank: dict = {}
    invalid_rank = raw_rank is not None and not isinstance(raw_rank, dict)
    if isinstance(raw_rank, dict):
        for key in RANK_SCORE_FIELDS:
            if key not in raw_rank:
                continue
            value = raw_rank[key]
            valid = _finite_number(value)
            if key.startswith("confidence") and valid:
                valid = 0 <= value <= 1
            if valid:
                rank[key] = value
            else:
                invalid_rank = True
        if "match_type" in raw_rank:
            match_type = raw_rank["match_type"]
            if _text(match_type) is None:
                invalid_rank = True
            else:
                rank["match_type"] = match_type

    raw_datasource = result.get("datasource")
    datasource = {}
    if isinstance(raw_datasource, dict):
        datasource = {
            key: text for key in DATASOURCE_FIELDS
            if (text := _text(raw_datasource.get(key))) is not None
        }

    result_type = result.get("result_type")
    if _text(result_type) is None:
        result_type = None
    reasons = []
    reason_codes = []

    def flag(code: str, reason: str) -> None:
        reason_codes.append(code)
        reasons.append(reason)

    if result_type not in ("building", "amenity"):
        flag("result_type_not_precise", "The result is not at building or amenity level.")
    if "housenumber" not in components:
        flag("missing_housenumber", "The result is missing a house number.")
    if "street" not in components:
        flag("missing_street", "The result is missing a street.")
    if coordinates is None:
        flag("invalid_coordinates", "Coordinates are missing or invalid.")
    if rank.get("confidence") != 1:
        flag("confidence_not_one", "The confidence score is missing, invalid, or below 1.")
    for level in ("city", "street", "building"):
        field = f"confidence_{level}_level"
        if field in rank and rank[field] < 1:
            flag(
                f"{field}_below_one",
                f"The {level}-level confidence score is below 1.",
            )
    if rank.get("match_type") != "full_match":
        flag("not_full_match", "The match type is not full_match.")
    if invalid_rank:
        flag("invalid_rank", "Some rank metadata is invalid.")
    return {
        "formatted": _text(result.get("formatted")),
        "coordinates": coordinates,
        "components": components,
        "result_type": result_type,
        "rank": rank,
        "datasource": datasource,
        "assessment": "needs_review" if reasons else "meets_rules",
        "reason_codes": reason_codes,
        "reasons": reasons,
        "duplicate_of": None,
    }


def _duplicate_key(result: dict) -> str | None:
    # Canonical JSON ignores object key order but distinguishes true from 1,
    # and 1 from 1.0. Every raw field participates, including unknown metadata.
    # Nonfinite values can occur in direct library calls; this key stays internal.
    try:
        return json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError, RecursionError):
        # Unsupported non-JSON library input must never be merged by accident.
        return None


def review_response(address: str, payload: dict) -> dict:
    """Explain review flags without claiming address validity or deliverability."""
    validate_input(address)
    results = _results(payload)
    candidates = []
    reasons = []
    first_occurrences: dict[str, int] = {}
    distinct_indices = []
    for index, result in enumerate(results, 1):
        candidate = _candidate(result)
        key = _duplicate_key(result)
        duplicate_of = first_occurrences.get(key) if key is not None else None
        candidate["duplicate_of"] = duplicate_of
        candidates.append(candidate)
        if duplicate_of is None:
            distinct_indices.append(index)
            if key is not None:
                first_occurrences[key] = index

    selected_candidate = None
    if not results:
        status = "no_result"
        reasons.append("Geoapify returned no candidates.")
    else:
        qualifying = [
            index for index in distinct_indices
            if candidates[index - 1]["assessment"] == "meets_rules"
        ]
        status = "needs_review"
        if not qualifying:
            reasons.append("No distinct candidate meets all of the tool's review rules.")
        elif len(qualifying) > 1:
            reasons.append("Multiple distinct candidates meet the rules; choose one after review.")
        else:
            index = qualifying[0]
            alternatives = [other for other in distinct_indices if other != index]
            if all(
                candidates[other - 1]["result_type"] in COARSE_RESULT_TYPES
                for other in alternatives
            ):
                status = "candidate_found"
                selected_candidate = index
                reasons.append(f"Candidate {index} meets the tool's review rules.")
                if alternatives:
                    reasons.append("All other distinct results are explicitly coarse alternatives.")
            else:
                reasons.append(
                    f"Candidate {index} meets the rules, but other distinct candidates "
                    "are not explicitly coarse; review the alternatives."
                )
        duplicate_count = len(candidates) - len(distinct_indices)
        if duplicate_count:
            noun = "result" if duplicate_count == 1 else "results"
            reasons.append(
                f"{duplicate_count} exact duplicate {noun} did not affect the decision."
            )
    return {
        "input": address,
        "status": status,
        "reasons": reasons,
        "candidate_count": len(candidates),
        "distinct_candidate_count": len(distinct_indices),
        "selected_candidate": selected_candidate,
        "candidates": candidates,
        "notice": NOTICE,
    }
