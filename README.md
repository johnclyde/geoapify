# Address Review CLI

A small Python tool that makes Geoapify geocoding results easier to review. Give it one address; get a readable report or JSON with candidate addresses, coordinates, match metadata, and reasons to check each result.

This is a conservative review heuristic. It does not certify postal deliverability, occupancy, unit numbers, or correctness of every address component. A single returned candidate does not prove that an address is unique across the dataset.

## Try it without an API key

Requires Python 3.11 or later. The runtime and tests use only the Python standard library.

From the repository root:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json --format text
```

The fixture is illustrative synthetic data, not a captured Geoapify response. Fixture mode makes no network request and needs no API key.

Use `--format json`, or omit `--format`, for machine-readable output. Both formats contain the same assessment. Reports identify whether the evidence came from a fixture or a live request.

## Query Geoapify

Set `GEOAPIFY_API_KEY` in your environment, then run:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --country us
```

A live run sends the supplied address to Geoapify. The tool makes one HTTPS request and does not retry. It requests up to three JSON results, disables IP-based country bias, and applies an explicit country filter when supplied. `--timeout` sets the socket timeout in seconds, with a default of `10`. The API key goes in the `x-api-key` header rather than the request URL.

For an installed command, create a virtual environment and install the package:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
address-review --help
```

## Read the result

| Status | Meaning |
| --- | --- |
| `candidate_found` | One distinct candidate meets all checks; any other distinct results identify only broader areas or streets. |
| `needs_review` | No candidate meets all checks, or another possible building or unknown result still needs comparison. |
| `no_result` | A valid response contains an empty `results` array. |

A candidate meets the rules when it describes a `building` or `amenity`, contains a street and house number, has finite coordinates within geographic bounds, has overall confidence exactly `1`, and has `rank.match_type` equal to `full_match`. Every supplied city, street, or building confidence score must also equal `1`. Those component scores are optional, but a conflicting or invalid score cannot be ignored. Missing required evidence or invalid rank metadata causes review.

Each candidate has an `assessment`, readable `reasons`, and stable `reason_codes`. A matching building plus a broader street result can produce `candidate_found`. A second building, amenity, or unknown result still requires review, even if its confidence is lower. The allowed broader levels are `street`, `suburb`, `district`, `city`, `county`, `state`, `postcode`, and `country`.

Only identical raw response objects are counted once. All returned rows remain visible; `duplicate_of` points to the first identical row. `candidate_count` counts all rows, `distinct_candidate_count` excludes identical duplicates, and `selected_candidate` is the one-based row index chosen by the rules, or `null`. Similar addresses or coordinates alone never establish a duplicate.

These are this project's rules, not a Geoapify accuracy guarantee. In particular, `full_match` describes the address level and does not mean every component is correct. The rules have not been calibrated against live results.

The CLI adds `source` (`fixture` or `live`), `country_filter`, and `tool_version` to the JSON report. In fixture mode the filter is always `null`: `--country` does not refilter saved results.

Completed review reports go to standard output and exit with code `0`, including `needs_review` and `no_result`. Consumers must inspect `status`. Errors go to standard error as JSON: code `2` for input, key, or unreadable/invalid-JSON fixtures; code `1` for API errors or an invalid response envelope, including fixture envelopes. A malformed response is never reported as an empty search result.

## Test and inspect

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use synthetic fixtures and mocked HTTP behavior. No live API key is required. Live Geoapify behavior has not been verified for this version.

- [Walkthrough](docs/walkthrough.md): run the example and understand the review rules.
- [Live evaluation plan](docs/live-evaluation.md): preview ten public-address scenarios without making requests, then opt into a bounded run when a key is available.
- [AI development log](docs/ai-development-log.md): implementation brief, decisions, and verification boundaries.
- [OpenAPI feedback](docs/openapi-feedback.md): concrete observations from the specification and official documentation.
- [Forward Geocoding specification](specs/forward-geocoding.json): the reviewed OpenAPI input, with [source and checksum](specs/README.md).

The scope is one address-review command, one API integration, reproducible local tests, and a separate ten-case evaluation script. There is no hosted application, general bulk-processing interface, runtime LLM, or MCP integration.

## License and attribution

Project code is [MIT licensed](LICENSE). The bundled Geoapify specification retains its [upstream MIT license](specs/LICENSE.geoapify). API data keeps its own source attribution and license; the project's code license does not relicense that data. Preserve any returned `datasource` attribution when using real results.

API reference: [Geoapify Forward Geocoding documentation](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/).
