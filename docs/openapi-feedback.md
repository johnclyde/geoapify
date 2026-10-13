# Forward Geocoding OpenAPI feedback

Reviewed inputs: the bundled [OpenAPI 3.1.0 specification, API version 1.1.1](../specs/forward-geocoding.json) and [Geoapify's official Forward Geocoding documentation](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/).

These observations come from reading the schema and documentation while building a small Python client. They are not claims of live service defects. No live API behavior was tested for this version.

## 1. Include match semantics next to the enum

`components.schemas.GeocodingRank.properties.match_type` enumerates values such as `full_match` but has no description of their meaning. The official response documentation explains that this reflects the address level, not whether every component is correct.

**Suggestion:** copy that distinction into the schema property's description and include an example of a level match that still needs review. This would help AI coding tools avoid turning `full_match` into an unconditional validation result.

## 2. Encode confidence bounds

The four confidence properties in `GeocodingRank` are typed as numbers without minimum or maximum values. The documentation describes a range from zero to one.

**Suggestion:** add `minimum: 0` and `maximum: 1`, plus a short description distinguishing overall, city, street, and building confidence. Keep optionality explicit. This would improve generated validation and make missing confidence easier to handle deliberately.

## 3. Make filter and bias serialization explicit

The `filter` and `bias` query parameters use array schemas without an explicit serialization style or `explode` setting. The official documentation describes a single value with pipe-separated clauses, such as a rectangle combined with a country filter.

**Suggestion:** express that wire format explicitly, for example with appropriate `pipeDelimited` serialization or a documented string representation, and add a complete multi-clause request example. The current array shape alone leaves client generators without the documentation's pipe-separator guidance. This PoC avoids the ambiguity by sending one clause per parameter.

## 4. Bring default country bias into the schema

The `bias` parameter's description only identifies ranking bias. The human-readable documentation has a separate note that the API defaults to IP-based country prioritization and that `countrycode:none` disables it.

**Suggestion:** include the effective default and opt-out example in the parameter description. This would help an assistant produce reproducible queries across developer machines and servers without needing to discover the separate note.

## 5. Add examples with deliberately missing fields

`GeocodingProperties` and `GeocodingRank` do not require every property. This agrees with the documentation's warning that available details depend on location type. A detailed successful example alone does not show how callers should handle a city-only match or absent rank metadata.

**Suggestion:** add examples for an empty `results` array, a city-level match, and a candidate without optional confidence fields. These would give AI coding tools useful counterexamples to copying a fully populated response shape into required application fields.

## What helped

The named JSON response envelope, separate error responses, explicit result type enum, and distinction between free-form and structured input provided clear implementation boundaries. The official explanations of match level and country bias supplied the semantic details needed for the review policy. Preserving those details directly in the OpenAPI descriptions would make the specification more self-contained for this kind of experiment.
