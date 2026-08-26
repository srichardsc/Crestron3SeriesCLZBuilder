# Changelog

## [Unreleased]

## [1.2] - 2026-08-26

First publicized update since 1.0.0; includes everything shipped in the
interim internal releases (previously listed as 1.1.0/1.2.0/1.2.1).

### Added

- One-command build: `crestron-clz run` (or `scripts\Run.ps1`). Drop a driver
  folder, open a terminal there, run it: on first use it creates the project
  configuration and the initial toolchain lock automatically; every later use
  increments `assembly.version` so Crestron Home accepts the uploaded package
  as an update, then compiles, signs with the official SDK service and
  publishes both series targets.
- Automatic version bump (`bump_version`) with `--no-bump` opt-out; non-numeric
  versions are rejected instead of silently skipping the bump.
- Guided first-run wizard: `crestron-clz setup` checks the host against every
  toolchain input, creates the project configuration, writes the toolchain lock
  when everything is present, and prints the exact next build command.
- Full-checklist diagnostics: `doctor` (human mode) reports ALL missing inputs
  at once, each with the expected location, why it matters, and an actionable
  fix, grouped into public vs licensed components.
- Numbered build stages (`[3/10] stage: ...`) plus a final summary with assembly
  and CLZ SHA-256 hashes, per-target file counts, elapsed time, and explicit
  SIMPL Windows import next steps.
- `scripts/MakeExecutable.ps1`: builds a single-file Windows executable
  (`clz-builder.exe`) so end machines need no Python installation.
- `docs/FOR-DUMMIES.md`: zero-knowledge step-by-step guide from clone to
  SIMPL Windows import, including a symptom-based troubleshooting table.
- `--version` flag on the CLI; doctor JSON reports now include the version.
- Concise environment setup guide in the README ("prepare this PC") and a
  TL;DR two-liner at the top of the first-time guide.

### Changed

- Human-readable doctor output replaced the terse key=value report (use
  `doctor --json` for the previous machine contract).
- Exit code for a host with missing toolchain inputs is consistently `2`
  in both human and JSON doctor modes.
- README leads with the automatic-version-bump benefit: every uploaded package
  is accepted by Crestron Home as an update without manual edits.

## [1.0.0] - 2026-08-23

- Added generic, configuration-selected SIMPL# and optional SIMPL+ builds.
- Added official SDK verification/signing, deterministic CLZ packaging,
  toolchain discovery/cache/lock, reproducibility gates, and transactional
  publication.
- Added Windows PowerShell 5.1 setup/build helpers, unit tests, public CI, and
  complete installation, configuration, security, and troubleshooting guides.
