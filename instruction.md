# Reconstruct the checkout requests

A checkout regression is changing both validation behavior and the bytes sent to the server. The attached capture is the browser-side evidence from one build. Reconstruct every recorded submission attempt from the state that was actually visible at that moment.

Everything needed for the incident is under `/app/data`. Read `capture_note.md` first; that note covers the first two phases only. The first sixty intents come from a chronological DOM mutation log. `q061` through `q096` come from a concurrent-render journal that contains committed and stale branches, so recorder file order is not a state history. After that, the capture switches to real interaction tasks. `event_note.md` describes the listener registry, independent recorder clocks, and event/microtask evidence for the final seventy-two rows. That phase starts from the complete `q096` state and remains stateful from one interaction to the next; recorder file order and query-id order are not browser chronology. `/app/collect_formdata.py` is an old triage helper and only covers the easy direct-input case.

Write `/app/output/submission_requests.json`. The contract below is normative.

The top-level value has exactly one key, `queries`. It contains one row for every record in `submit_intents.ndjson`, followed by one row for every record in `event_intents.ndjson`. Each row has exactly `query_id`, `validation_performed`, `invalid_ids`, `would_submit`, `entry_manifest`, and `request`. Every query id appears once; top-level row order is not significant.

A text entry has exactly `name`, `kind`, and `value`, with `kind` equal to `"text"`. A file entry has exactly `name`, `kind`, `filename`, `mime`, `size`, and `sha256`, with `kind` equal to `"file"`. `size` is the byte count and `sha256` is the lowercase SHA-256 of the captured file bytes. `entry_manifest` is the normalized successful-entry list for the reconstructed state, not a dump of raw control state. Build this manifest for every intent, even when validation or event cancellation stops the request. Textarea line endings are normalized to CRLF when the entry is constructed; that normalized string is what appears in the manifest and what is serialized.

The live values in `runtime.ndjson` are capture facts. Do not run a second browser value-sanitization pass over them. A captured nonnumeric string on a `number` input remains that string for successful-entry construction; validation can still reject it when validation is performed.

A non-null `request` has exactly `method`, `url`, `content_type`, `body_len`, and `body_sha256`. For GET, `content_type` is JSON `null`, `body_len` is `0`, and `body_sha256` is the SHA-256 of the empty byte string. For POST, `content_type` is the effective request content type. `invalid_ids` and `entry_manifest` are ordered. Do not add diagnostic fields.

Use ordinary HTML form ownership, successful-control, constraint-validation, DOM event-dispatch, URL-resolution, and serialization behavior except for the capture-specific behaviors stated in `capture_note.md` and `event_note.md`. The evidence files, not the final DOM alone, determine the answer.

You can replace the starter helper or ignore it. Only the JSON artifact is graded.

You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
