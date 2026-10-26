---
name: scope-guard
description: Keep coding-agent edits within an explicit repository allowlist.
---
# Scope guard
1. Read .steadfast/policy.json before editing.
2. Check planned paths with steadfast scope-check --changed PATH.
3. Reject absolute paths, traversal paths, and paths outside allowed_paths.
4. Do not broaden the allowlist to accommodate an unapproved change.
5. Preserve existing integration files and user configuration by default.
6. Run scope checks after changes and report blocked paths.
