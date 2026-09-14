# Capture format and chronology

This is a synthetic browser-side capture of a checkout incident. Its shape mirrors evidence a browser-platform or senior frontend engineer would see: an initial DOM, live control state, custom-element state, historical mutations, concurrent render commits, submission triggers, and request metadata.

`nodes.ndjson` is the initial DOM snapshot. Each row has a stable capture `id`, a `parent` capture id (or null), global document `order`, lower-case `tag`, and normalized `attrs`. Attribute values are strings unless the capture explicitly stores a Boolean; only JSON `true` means a Boolean attribute is present. Capture ids are not HTML `id` attributes.

`runtime.ndjson` is the initial live state for native controls and options. `face_state.ndjson` is the initial state exposed by form-associated custom elements; file entries point below `/app/data`, and those bytes are authoritative.

For `q001` through `q060`, `mutations.ndjson` is the chronological change log after the initial snapshot. Apply its records in file order through the sequence in `intent_timeline.ndjson`. `set_attr` sets or removes an attribute, `set_runtime` patches live state, `set_parent` reparents a node, `insert_node` adds a node, and `set_face` patches custom-element state. Relationships such as form ownership and disabledness can therefore change over time.

The recorder changed mode after `q060`. For later query ids, the baseline is the complete state at `q060`. `render_journal.ndjson` contains concurrent render commits flushed by several recorder buffers. Its file order and `flush_seq` are recorder order, not commit order. Each commit names its single `parent` and carries a list of patches using the same operation shapes as `mutations.ndjson`. `render_heads.ndjson` gives the active commit head for each later query. A later query sees exactly the patches on that head's ancestor lineage back to `base-q060`, applied from ancestor to descendant; sibling, stale, and superseded commits that are not on that lineage are not visible. Heads can move back to an ancestor or onto a sibling branch.

`submit_intents.ndjson` identifies the target form by HTML id, the recorded submitter capture id when one existed, image coordinates when relevant, and the multipart boundary observed for that attempt. If the recorded submitter is not associated with the target form in the reconstructed state, treat the form as having no submitter. `request_context.json` contains the document base URL.

Two compatibility behaviors were present in this build. First, a GET submission preserves an existing action query and appends the generated form query with `&` when both are non-empty; fragments are dropped. Second, an option disabled directly or by a disabled ancestor `optgroup` is unavailable both as a successful select entry and to this build's required-select check. A required select is invalid when it has no available selected option with a non-empty value.

The old `/app/collect_formdata.py` predates the mutation timeline, concurrent render journal, and custom elements. It is useful for seeing file shapes, not as a complete implementation.
