---
name: python-release-breakage
description: Diagnose Python package failures after publishing by inspecting wheel and sdist contents, metadata, entry points, dependency constraints, and clean-environment installs.
---
# Python release breakage diagnosis

Use when a package works from a checkout but fails after installation, ships missing files, exposes a broken CLI, or behaves differently from source.

## Procedure
1. Record package name, exact version, index URL, Python and platform versions, install command, traceback, and whether the wheel, source distribution, or both are affected. Never assume the latest version is the failing one.
2. Download the exact published wheel and source distribution into a temporary directory. Inspect archive listings and metadata before importing or executing package code.
3. Compare archive contents against source: modules, templates, schemas, typing markers, license/readme files, generated assets, and package-data rules. Identify files present in Git but absent from the artifacts.
4. Inspect METADATA or PKG-INFO, Requires-Python, runtime dependencies, extras, console-script entry points, project name, version, and build backend. Compare with pyproject.toml and intended compatibility.
5. Reproduce in a fresh temporary virtual environment. Install the exact published version from the intended index, run pip check, invoke the installed console script with --help, then run the smallest reproducer. Run outside the repository so local imports cannot mask packaging defects.
6. Separate package installation, import, CLI entry-point, optional-extra, and runtime behavior failures. Record which layer is actually broken.
7. Fix build configuration, package-data rules, entry points, version metadata, or dependency constraints at the source. Do not patch extracted artifacts or indiscriminately include every repository file.
8. Build wheel and sdist from a clean tree, inspect both archives, install each in fresh environments, and run the reproducer and relevant tests.
9. Confirm tested artifacts correspond to the intended commit and version. Do not publish, retag, or overwrite a release without explicit authorization.
10. Report the exact artifact, reproduction, missing or mismatched content, changed paths, clean-install results, platform gaps, and any uncertainty.

## Diagnostic shortcuts
- ModuleNotFoundError only after installation: inspect archive contents and package discovery first.
- CLI command missing after install: inspect console-script metadata and PATH.
- Works in checkout but fails in a clean environment: inspect source-tree imports, undeclared dependencies, and generated files.
- Only one Python version fails: inspect Requires-Python, syntax/runtime API compatibility, and dependency markers.
- Source distribution fails while wheel works: inspect sdist inclusion rules and build-time requirements.

## Acceptance criteria
- The exact artifact failure is reproduced or explicitly marked not reproduced.
- Wheel and sdist contents and metadata are inspected rather than inferred from source.
- Fix includes a clean-environment regression check.
- Publishing remains a separate, explicitly authorized action.
