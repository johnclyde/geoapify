# Address Review CLI

A small Python tool that makes Geoapify geocoding results easier to review. Give it one address; get JSON with candidate addresses, coordinates, match metadata, and reasons to check the result.

This is a conservative review heuristic. It does not certify postal deliverability, occupancy, unit numbers, or correctness of every address component. A single returned candidate does not prove that an address is unique across the dataset.

## Try it without an API key

Requires Python 3.11 or later. The runtime and tests use only the Python standard library.

From the repository root:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json
```

The fixture is illustrative synthetic data, not a captured Geoapify response. Fixture mode makes no network request and needs no API key.

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
| `candidate_found` | Exactly one returned result meets all of the conservative checks below. |
| `needs_review` | Results exist, but there are multiple candidates, missing details, or other reasons for human review. |
| `no_result` | A valid response contains an empty `results` array. |

`candidate_found` requires a `building` or `amenity`, a street and house number, finite coordinates within geographic bounds, overall confidence exactly `1`, and `rank.match_type` equal to `full_match`. Missing required review evidence or invalid rank metadata causes review. These are this project's rules, not a Geoapify accuracy guarantee. In particular, `full_match` describes the address level and does not mean every component is correct.

Completed review reports go to standard output and exit with code `0`, including `needs_review` and `no_result`. Consumers must inspect `status`. Errors go to standard error as JSON: code `2` for input, key, or unreadable/invalid-JSON fixtures; code `1` for API errors or an invalid response envelope, including fixture envelopes. A malformed response is never reported as an empty search result.

## Test and inspect

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use synthetic fixtures and mocked HTTP behavior. No live API key is required. Live Geoapify behavior has not been verified for this version.

- [Walkthrough](docs/walkthrough.md): run the example and understand the review rules.
- [AI development log](docs/ai-development-log.md): implementation brief, decisions, and verification boundaries.
- [OpenAPI feedback](docs/openapi-feedback.md): concrete observations from the specification and official documentation.
- [Forward Geocoding specification](specs/forward-geocoding.json): the reviewed OpenAPI input, with [source and checksum](specs/README.md).

The scope is one command, one API integration, and reproducible local tests. There is no hosted application, bulk processing, runtime LLM, or MCP integration.

## License and attribution

Project code is [MIT licensed](LICENSE). The bundled Geoapify specification retains its [upstream MIT license](specs/LICENSE.geoapify). API data keeps its own source attribution and license; the project's code license does not relicense that data. Preserve any returned `datasource` attribution when using real results.

API reference: [Geoapify Forward Geocoding documentation](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/).
