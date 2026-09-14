# Form Wire Audit

A browser form-submission and HTTP wire-format reconstruction challenge focused on standards-compliant form behavior and exact request serialization.

The project exercises the full path from DOM form state to the bytes emitted on the wire. A correct implementation must determine which controls participate in submission, apply validation and submitter rules correctly, and serialize the resulting form data according to the selected encoding and HTTP method.

## Overview

HTML form submission involves substantially more than collecting every input inside a `<form>` element.

Submission behavior depends on:

- form ownership
- disabled controls and disabled fieldsets
- the first-legend exception
- successful-control rules
- radio-button groups
- select-option availability
- form-associated custom elements
- constraint validation
- submitter-specific overrides
- `formnovalidate`
- HTTP method selection
- URL construction
- character encoding
- multipart boundaries
- file contents

This project audits those behaviors together as one end-to-end pipeline.

## Repository Structure

```text
form-wire-audit/
├── cheat/
├── environment/
├── solution/
├── tests/
├── instruction.md
└── task.toml
```

### `instruction.md`

Defines the required form-processing behavior, submission rules, and output contract.

### `environment/`

Contains the reproducible runtime and task data used by the challenge.

### `solution/`

Contains the reference implementation used to validate expected behavior.

### `tests/`

Contains the verifier and conformance tests.

### `task.toml`

Contains task metadata and execution configuration.

## What the Task Covers

### Form Ownership

Controls are not necessarily owned by the nearest form in the DOM.

The implementation must account for explicit form association and determine the correct owner before deciding whether a control can participate in submission.

### Disabled Controls

Disabled controls generally do not contribute form data.

Special care is required for disabled fieldsets because descendants of the fieldset's first `legend` may remain eligible while other descendants are excluded.

### Constraint Validation

Submission behavior depends on browser-style validation semantics.

This includes cases such as:

- required controls
- radio groups
- unavailable choices
- controls excluded from validation
- submitter-dependent validation bypass

A submitter using `formnovalidate` can alter whether constraint validation blocks the submission.

## Successful Controls

Only successful controls contribute entries to the form-data set.

The implementation must correctly handle controls such as:

- text inputs
- checkboxes
- radio buttons
- select elements
- textareas
- buttons
- file inputs
- custom form-associated elements

DOM presence alone is not enough to determine whether a value is submitted.

## Submitter Overrides

The element that initiates submission can override properties of the owning form.

Relevant behavior includes overrides for:

```text
formaction
formmethod
formenctype
formtarget
formnovalidate
```

The effective request therefore depends on both the form and the active submitter.

## Request Construction

After the form-data set is constructed, the task converts it into the appropriate HTTP representation.

### GET

GET submissions require correct query-string construction and URL handling.

### POST

POST requests depend on the selected encoding type.

Supported wire formats include:

```text
application/x-www-form-urlencoded
multipart/form-data
text/plain
```

## URL Encoding

URL-encoded submissions require deterministic handling of:

- field ordering
- character encoding
- spaces
- reserved characters
- repeated field names
- empty values
- UTF-8 content

The goal is to reproduce the browser-visible request rather than produce merely equivalent application data.

## Multipart Form Data

Multipart serialization introduces additional wire-level details.

A correct result must preserve:

- part ordering
- multipart boundaries
- content-disposition metadata
- field names
- filenames
- file bytes
- line endings
- UTF-8 text

Multipart output is therefore validated as a serialization problem rather than only as a parsed key/value map.

## File Inputs

File controls require preserving actual file payloads rather than replacing them with filenames or textual placeholders.

The resulting multipart request must maintain the expected metadata and byte content.

## Text/Plain Encoding

`text/plain` form submission follows different serialization rules from standard URL encoding.

The implementation must therefore treat encoding type as part of the submission algorithm rather than applying one generic encoder to every request.

## Processing Pipeline

Conceptually, the task follows this flow:

```text
DOM / form state
        ↓
resolve form ownership
        ↓
determine active submitter
        ↓
constraint validation
        ↓
successful-control filtering
        ↓
construct form-data entries
        ↓
apply method / action / enctype
        ↓
serialize request
        ↓
produce final wire representation
```

Each stage affects later stages, so small semantic mistakes can produce a request that looks plausible while still being incorrect.

## Technical Focus

The project exercises:

- HTML form semantics
- DOM reasoning
- browser behavior
- constraint validation
- HTTP request construction
- URL encoding
- multipart serialization
- UTF-8 handling
- binary file preservation
- standards-oriented testing
- deterministic serialization

## Validation

The verifier checks observable submission behavior rather than merely checking that a request contains approximately the right values.

Correctness can depend on:

- which fields are present
- which fields are absent
- entry ordering
- method and target URL
- selected encoding
- exact text encoding
- multipart structure
- file content

This makes the project useful for testing both browser-semantics knowledge and low-level request construction.

## Goal

The goal is to reconstruct a submission pipeline that behaves consistently with browser form semantics from DOM state through final HTTP representation.

A robust solution should derive its result from the documented form state and submission rules rather than relying on hard-coded examples.

## License

No license is currently specified.
