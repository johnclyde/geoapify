# Reviewing one address with Geoapify and Python

Geocoding can return a convincing display address even when the result only identifies a street or city. Address Review CLI keeps the evidence visible: the candidate address, coordinates, result type, confidence metadata, and specific reasons for review. It uses Geoapify's Forward Geocoding API with a small, explicit local policy.

The review command accepts one address at a time. A separate, bounded evaluation script can exercise ten prepared scenarios. The project has no web server, database, or runtime AI dependency. Use Python 3.14 or later for the offline example and tests.

## 1. Start with the offline example

From the repository root, run:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json --format text
```

The input names a public location. The fixture is manually constructed, illustrative data shaped like a Geoapify JSON response. It is not a recorded live result, a measurement of geocoder quality, or evidence that the service will return the same candidate today. This mode runs the same response interpretation without sending a request or requiring credentials.

The single candidate includes the fields required by the local policy, so the report's status is `candidate_found`. The readable report labels the source as an offline fixture and gives a next step. Omit `--format text` to get JSON instead. Inspect the report's metadata and reasons as well as its status. Success here means the example passes a known rule set.

## 2. Understand the decision

The tool requests up to three candidates and assesses each independently. A candidate meets the rules only when it describes a building or amenity, includes a street and house number, has valid coordinates, has overall confidence `1`, and carries `full_match` metadata. Every supplied city, street, or building confidence score must also equal `1`; omitted component scores remain optional.

Exactly identical raw response objects count once, with all rows preserved in the report. One qualifying building plus a broad street result can yield `candidate_found`. A second possible building or an unknown result type keeps the overall verdict at `needs_review`, even if that alternative has a weaker score. The rules never silently pick the first of two possible buildings.

Try `examples/strong-with-coarse.json` to see a selected building alongside a street result. Then try `examples/conflicting-confidence.json`: its overall confidence is `1`, but a lower building score causes review. Each candidate lists its own `assessment`, `reason_codes`, and readable `reasons`. `selected_candidate` is a one-based row index, or `null` when no choice is made.

The [official response documentation](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/#response-object) explains that match type concerns the address level. It does not establish the correctness of every component. This is why the tool checks several pieces of evidence and labels the outcome `candidate_found` rather than claiming an address is certified.

Missing review evidence or invalid candidate metadata causes `needs_review`. A valid empty result list produces `no_result`. Invalid JSON or an incorrect response envelope produces an error instead of pretending that no address exists. Missing information and broken data have different implications for callers.

## 3. Make a live request

Provide `GEOAPIFY_API_KEY` through your environment, then omit `--fixture`:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --country us --timeout 10 --format text
```

This sends the input address to Geoapify. The client selects `format=json`, limits results to three, and sets `bias=countrycode:none` so request location does not silently choose a preferred country. `--country us` adds a hard country filter. Each invocation makes one request, with no retries.

Live service behavior has not been verified for this version. The offline tests establish local behavior, including simulated network failures; they cannot establish current coverage, account access, or live response quality.

The [evaluation plan](live-evaluation.md) prepares ten variations of a public address. Its default mode prints the plan without using a key or sending any requests. Live results, when collected, are observations rather than a measured accuracy benchmark.

## 4. Use the output responsibly

Normal reports go to standard output, as JSON by default or readable text with `--format text`. All three review statuses exit successfully, so an automation must inspect the JSON `status` instead of treating exit code zero as address approval. Errors are always JSON on standard error, including in text mode. Exit code `2` identifies input, key, or fixture-reading problems; `1` identifies API failures or invalid response envelopes, including fixture envelopes.

A single returned candidate is not proof of global uniqueness. This tool also does not verify mail delivery, apartment numbers, occupancy, or whether the user intended that location. Keep source attribution with real API data.

## 5. Reproduce the development checks

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Codex assisted with implementation and tests using the bundled OpenAPI specification and official documentation. The [development log](ai-development-log.md) explains the technical brief and decisions. The [feedback notes](openapi-feedback.md) distinguish specification observations from live behavior and suggest small documentation changes that would help future AI-assisted clients.
