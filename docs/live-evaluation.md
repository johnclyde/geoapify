# Bounded live observation plan

The repository includes ten observation inputs derived from one public civic address, `200 Larkin Street, San Francisco, CA 94102, United States`. The [Asian Art Museum's official contact page](https://about.asianart.org/contact-us/) confirms this baseline address. These are ten variations of one location, not ten independent locations. They vary spelling, abbreviations, missing components, and conflicting components or filters. The [case file](../examples/live-cases.json) contains no private addresses and no expected accuracy labels.

**No live results have been collected for this plan.** The harness is prepared and tested with a mocked client. Running its default mode does not use an API key or send a request.

## Inspect the plan

From the repository root with Python 3.14 or later:

```sh
PYTHONPATH=src python scripts/evaluate.py
```

The JSON output identifies `mode: "dry_run"`, `status: "planned"`, and zero attempted requests. Each observation has `outcome: "not_run"`. This output is a plan, not evidence of service behavior.

## Run the ten observations

Set `GEOAPIFY_API_KEY` in your environment, then explicitly opt in:

```sh
PYTHONPATH=src python scripts/evaluate.py --live
```

To save the report locally:

```sh
PYTHONPATH=src python scripts/evaluate.py --live > live-evaluation.json
```

That second command is another live run. Choose one command; running both sends the requests twice. Avoid committing reports before inspecting their content and preserving source attribution.

The harness validates the whole case file before starting. It accepts at most ten cases, uses one client call per case, waits one second after a completed call before beginning the next, and never retries. It stops on the first failure, including authentication, quota, network, or malformed-response errors. Unattempted cases are marked `skipped` after a failure. Each call uses the existing client with a ten-second socket timeout.

## Read the report

Every report records its format version, tool version, mode, UTC start and completion timestamps, and the number of planned and attempted client calls. A failed client call might never reach Geoapify, so `attempted_requests` is not a billing or server-side request count.

Each completed observation contains its input, country filter, scenario, timestamps, and the full review report produced by the existing tool. An observation can complete normally with `candidate_found`, `needs_review`, or `no_result` inside that report. These outcomes are measurements to inspect, not pass/fail labels for the scenario.

Errors record a bounded error code and an HTTP status where available. Raw exceptions, request URLs, and remote error bodies are omitted. The API key is never deliberately added to reports; any exact credential echoed in a string is redacted before printing.

Exit code `0` means the dry-run plan or live run completed. Code `1` means a live evaluation stopped after a client failure; its partial report remains on standard output. Code `2` means a setup or case-file error; an error object goes to standard error and no request is made.

## Limits

Ten variations of one address are a small behavior sample. They do not measure worldwide coverage, postal deliverability, dataset uniqueness, or an accuracy percentage. Even the intentionally implausible house number is an observation input, not proof that an address cannot exist. Different data revisions may produce different candidates.

The observations retain the tool's current review policy. They do not establish independent ground truth or validate that policy. This fixed experiment is not a general batch geocoding service.

Run the offline harness tests with:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_evaluation.py -v
```
