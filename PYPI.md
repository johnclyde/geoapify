# geoapify-address-review

Inspect one address with Geoapify and see why a returned candidate needs review. This command-line tool produces readable text or JSON containing candidate addresses, coordinates, match metadata, and an explanation for each assessment.

Version **0.2.0** is experimental. It requires **Python 3.14 or later**, has **no runtime dependencies**, and is an independent project, not an official Geoapify SDK. Local tests use synthetic fixtures and mocked HTTP responses. Live API behavior has not yet been verified.

## Install and run

```sh
pip install geoapify-address-review
```

Set `GEOAPIFY_API_KEY` in your environment, then run:

```sh
address-review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --country us --format text
```

This sends the address to Geoapify in one request. Use `--format json`, or omit `--format`, for structured output. `--country` restricts the search to a country; `--timeout` sets the socket timeout in seconds.

## Understand the report

| Status | Meaning |
| --- | --- |
| `candidate_found` | One distinct candidate meets the review rules; other distinct results identify only broader locations. |
| `needs_review` | Required evidence is missing or insufficient, or another possible address needs comparison. |
| `no_result` | A valid response contains no candidates. |

The rules consider location level, street and house number, coordinates, confidence, and match type. Each candidate includes readable reasons and stable reason codes. Identical response rows are marked as duplicates and counted once, while all returned rows remain visible.

`candidate_found` does not verify postal deliverability or the address the user intended. These rules are a conservative review aid, not an accuracy guarantee. Normal reports exit successfully for all three statuses, so automated callers must inspect `status`.

## Try an offline example

Example fixtures are available in the [source repository](https://github.com/johnclyde/geoapify/tree/main/examples), rather than installed with the package. To run one without an API key:

```sh
git clone https://github.com/johnclyde/geoapify.git
cd geoapify
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json --format text
```

The fixture contains illustrative synthetic data, not a recorded live response. This command makes no network request.

See the [walkthrough](https://github.com/johnclyde/geoapify/blob/main/docs/walkthrough.md) for interpretation and the [bounded evaluation plan](https://github.com/johnclyde/geoapify/blob/main/docs/live-evaluation.md) for ten observation scenarios.

Code is [MIT licensed](https://github.com/johnclyde/geoapify/blob/main/LICENSE). Returned API data retains its own source attribution and license.
