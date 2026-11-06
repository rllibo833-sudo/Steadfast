# Cross-platform ecosystem index

Steadfast can validate a canonical JSON index of projects distributed across GitHub, Notion, Supabase, local Termux storage, and other systems.

## Files

- `universe.json`: canonical project and source registry.
- `schema.json`: JSON Schema contract.
- `relationships.json`: provisional relationship graph projection.

## Run

From the Steadfast repository root:

```bash
python -m pip install -e .
steadfast universe-check
```

Use another manifest path with:

```bash
steadfast universe-check --manifest path/to/universe.json
```

The command prints a JSON report and returns exit code 1 when errors are found.

## What is checked

- Required top-level fields and JSON validity.
- Unique source IDs and project IDs.
- Project source references point to known source IDs.
- Each source reference has a URI.
- Relationship endpoints refer to known project IDs or the reserved `harness` and `ncm` nodes.
- Local source references are checked relative to the repository root.

## What is not checked

- HTTP(S) URLs are syntax-checked only; the command does not fetch them.
- Supabase, Notion, Cloudflare, and GitHub account state is not queried.
- No source repository, database, or project file is modified.
- The validator does not infer project completion or technical dependencies.

Harness can consume this report as deterministic validation input. An NCM adapter can later transform the validated manifest into a concept graph; that adapter is not part of this first implementation.
