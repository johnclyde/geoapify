# Offline examples

These JSON files are **hand-authored illustrative fixtures**, not captured API responses. They are shaped like Geoapify's `format=json` output and use a public civic address for context. Their coordinates, confidence scores, and alternative candidates are demonstration values. Do not treat them as evidence about the real address.

| File | Expected status | What it demonstrates |
| --- | --- | --- |
| `single-candidate.json` | `candidate_found` | One specific candidate passes this tool's conservative policy. |
| `ambiguous.json` | `needs_review` | More than one returned candidate requires human review. |
| `coarse-match.json` | `needs_review` | A street-level result is insufficient for a building address. |
| `no-result.json` | `no_result` | The API response contains an empty result list. |

From the repository root, no installation or API key is needed:

```sh
PYTHONPATH=src python -m geoapify_address_review \
  '200 Larkin Street, San Francisco, CA 94102, United States' \
  --fixture examples/single-candidate.json
```

Replace the fixture filename to try the other outcomes. Fixture mode never sends a request; `--country` does not refilter saved results. Tests use additional small in-memory fixtures to cover errors and missing metadata.
