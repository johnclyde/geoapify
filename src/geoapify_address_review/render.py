"""Readable reports that keep untrusted response text on one terminal line."""

import unicodedata


def _safe(value: object) -> str:
    text = str(value)
    return "".join(
        char if char.isprintable() and unicodedata.category(char) != "Cf"
        else char.encode("unicode_escape").decode("ascii")
        for char in text
    )


def render_text(report: dict) -> str:
    """Render the same evidence as JSON without interpreting terminal controls."""
    status = report["status"]
    labels = {
        "candidate_found": "Candidate found",
        "needs_review": "Needs review",
        "no_result": "No result",
    }
    fixture = report["source"] == "fixture"
    source = "fixture (offline; no request made)" if fixture else "live Geoapify response"
    country = (
        "not applied (fixture)" if fixture
        else report["country_filter"] or "none"
    )
    lines = [
        f"Address: {_safe(report['input'])}",
        f"Source: {source}",
        f"Country filter: {_safe(country)}",
        f"Result: {labels[status]} ({status})",
        f"Candidates: {report['candidate_count']} returned, "
        f"{report['distinct_candidate_count']} distinct",
    ]
    lines.extend(f"  - {_safe(reason)}" for reason in report["reasons"])
    for index, candidate in enumerate(report["candidates"], 1):
        assessment = candidate["assessment"].replace("_", " ")
        lines.extend([
            "",
            f"Candidate {index}: {_safe(candidate['formatted'] or '(no display address)')}",
            f"  Assessment: {assessment}",
        ])
        if candidate["duplicate_of"] is not None:
            lines.append(f"  Identical to candidate {candidate['duplicate_of']}; counted once.")
        if report["selected_candidate"] == index:
            lines.append("  Selected by the review rules.")
        lines.append(f"  Level: {_safe(candidate['result_type'] or 'missing')}")
        for key, value in candidate["components"].items():
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {_safe(value)}")
        coords = candidate["coordinates"]
        lines.append(
            f"  Coordinates: {coords['lat']}, {coords['lon']}" if coords
            else "  Coordinates: missing or invalid"
        )
        for key, value in candidate["rank"].items():
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {_safe(value)}")
        lines.extend(f"  - {_safe(reason)}" for reason in candidate["reasons"])
        for key, value in candidate["datasource"].items():
            lines.append(f"  Data {key}: {_safe(value)}")
    next_steps = {
        "candidate_found": "Check the selected candidate against the address you intended to use.",
        "needs_review": "Compare the candidates and resolve the listed review reasons before use.",
        "no_result": "Check the spelling and country, then try a more complete address.",
    }
    lines.extend(["", f"Next step: {next_steps[status]}", "", report["notice"]])
    return "\n".join(lines)
