# AI-assisted development log

This is a technical summary of implementation and follow-up review. It is not a verbatim transcript or a benchmark of the assistant. No API credentials or private correspondence are included.

## Inputs and tools

- AI coding assistant: Codex, with parallel implementation, tests, and documentation tasks.
- API input: bundled [Forward Geocoding OpenAPI specification](../specs/forward-geocoding.json), OpenAPI `3.1.0`, API specification version `1.1.1`; [source and checksum](../specs/README.md).
- Human-readable reference: [official Forward Geocoding documentation](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/), consulted to interpret country bias, optional fields, and match metadata.
- Execution: Python standard library, local fixture runs, and `unittest`; no runtime AI client or MCP server.

## Implementation brief

The current brief is a small Python 3.14+ command-line package that accepts one address and emits a review report. The package should support an API key from the environment, an optional country restriction, a configurable timeout, and a fixture mode requiring no key or network. Python 3.14 is the sole automated test target; supporting older Python versions is outside the scope.

The initial review policy required exactly one returned building or amenity with street, house number, valid coordinates, confidence `1`, and `full_match`. Follow-up work asked for assessments per candidate, readable terminal reports, and a small live evaluation plan. The current policy also checks supplied component confidence scores and distinguishes broader results from competing possible buildings. Public examples remain illustrative synthetic data. Tests cover response interpretation and failure paths.

## Decisions and interpretation checks

1. **Specify JSON explicitly.** The API's default output format is GeoJSON. The client requests `format=json` and expects the documented `results` envelope. Treating that envelope as required prevents a malformed response from becoming a false no-result report.
2. **Avoid accidental country preference.** The human-readable documentation states that request IP can supply a default country bias. The client explicitly disables it and uses a separate hard country filter when requested.
3. **Keep optional fields optional.** The schema does not require all candidate fields. Their absence supplies a reason to review, not invented values or automatic approval.
4. **Do not overread `full_match`.** The documentation describes address-level matching, not a guarantee that every component is correct. The policy combines it with other checks and makes no deliverability claim.
5. **Keep the experiment reproducible.** Synthetic fixtures and mocked HTTP failures exercise local behavior without credentials. No live responses are presented as fixtures.

These are documented design decisions and interpretation checks. They are not claims that a deployed integration failed or that a live API defect was reproduced.

## Corrections during review

An independent review reproduced two local edge cases after the first eight tests passed. Python's default JSON parser allowed `NaN` and `Infinity` in offline fixtures even though the HTTP parser rejected them. Fixture parsing now rejects those constants too. An escaped lone Unicode surrogate in a response also caused an output traceback; JSON output now escapes Unicode safely, and invalid Unicode input is rejected before request construction. Regression cases were added to the existing tests. These were implementation corrections, not Geoapify service failures.

The next review found that an overall confidence of `1` could hide a lower building-level confidence, and that any second result forced review even when it only described a street. Version `0.2.0` assesses each candidate, flags conflicting component scores, and selects a unique qualifying candidate only when the remaining distinct results are explicitly broader levels. A second possible building still requires review. Identical raw response rows count once; similar coordinates or formatted addresses are insufficient to merge candidates.

The follow-up also added `--format text`, fixture/live provenance, and a next step for each outcome. Readable output escapes control characters from input and response fields so they cannot create misleading terminal lines. JSON remains the default and errors remain JSON in either mode.

A separate [evaluation script](live-evaluation.md) prepares ten variations of one public civic address. Dry-run mode makes no requests; live mode requires an explicit option and an API key, caps the run at ten calls, spaces calls, and stops on failure. This is preparation for gathering observations, not evidence that the evaluation has been run.

## Verification and limits

Reproduce the offline checks from the repository root:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json
```

The tests validate the implementation's local rules and simulated failures. This version has not been validated against a live Geoapify request. The review thresholds are a conservative project policy, not a measured accuracy model. Changes to the API, dataset, or intended use may require a different policy.

The [OpenAPI feedback](openapi-feedback.md) records specific improvements suggested by comparing the bundled schema with the official documentation. No feedback has been represented here as already accepted by Geoapify.
