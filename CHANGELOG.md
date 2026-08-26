# Changelog

## [Unreleased]

## [1.1.0] - 2026-08-25

### Added

- Guided first-run wizard: `crestron-clz setup` checks the host against every
  toolchain input, creates the project configuration, writes the toolchain lock
  when everything is present, and prints the exact next build command.
- Full-checklist diagnostics: `doctor` (human mode) now reports ALL missing
  inputs at once instead of stopping at the first one, each with the expected
  location, why it matters, and the actionable fix, grouped into public vs
  licensed components.
- Numbered build stages (``[3/6] stage: ...``) plus a final summary with assembly
  and CLZ SHA-256 hashes, per-target file counts, elapsed time, and explicit
  SIMPL Windows import next steps.
- `scripts/MakeExecutable.ps1`: builds a single-file Windows executable
  (`clz-builder.exe`) so end machines need no Python installation.
- `docs/FOR-DUMMIES.md`: zero-knowledge step-by-step guide from clone to
  SIMPL Windows import, including a symptom-based troubleshooting table.
- `--version` flag on the CLI; doctor JSON reports now include the version.

### Changed

- Human-readable doctor output replaced the terse key=value report (use
  `doctor --json` for the previous machine contract).
- Exit code for a host with missing toolchain inputs is now consistently `2`
  in both human and JSON doctor modes.

## [1.0.0] - 2026-08-23

- Added generic, configuration-selected SIMPL# and optional SIMPL+ builds.
- Added official SDK verification/signing, deterministic CLZ packaging,
  toolchain discovery/cache/lock, reproducibility gates, and transactional
  publication.
- Added Windows PowerShell 5.1 setup/build helpers, unit tests, public CI, and
  complete installation, configuration, security, and troubleshooting guides.
