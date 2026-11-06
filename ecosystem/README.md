# Ecosystem Index

This directory is the canonical index for projects whose source code and records remain distributed across their original platforms.

- `universe.json` — canonical project and source registry.
- `schema.json` — validation contract for the manifest.
- `relationships.json` — provisional graph projection derived from the manifest.

## Rules

1. Do not copy or relocate project source code into this directory.
2. Keep one stable project ID per project across platforms.
3. Add a source reference only when its location is known.
4. Mark unknown status as `unverified`; do not infer completion from a document or repository existing.
5. Treat relationships as provisional until supported by source evidence.
6. Regenerate `relationships.json` from `universe.json` when the manifest changes.

## Current coverage

GitHub, Notion, and Supabase have been inventoried through connected integrations. Cloudflare and the live Termux filesystem are not yet synchronized.

Harness and NCM are listed as intended consumers, not as completed integrations.
