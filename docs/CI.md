# Continuous integration limitations

GitHub Actions can validate the open-source portion of this repository, but a
public runner normally does not have the licensed Crestron toolchain. CI must
not pretend to produce an accepted signed CLZ without those inputs.

## What public CI checks

- PowerShell script parsing and repository hygiene;
- Python syntax and project tests when the selected core provides them;
- configuration/schema checks that do not require SDK binaries;
- documentation and policy files;
- `git diff --check` and accidental generated/proprietary artifacts.

## What needs a licensed Windows host

- MSBuild against .NET Compact Framework 3.5;
- SPlusCC compilation of `.usp` modules;
- SIMPL# SDK assembly processing;
- official verification/signing service;
- deterministic CLZ validation against Cresdb resources;
- SIMPL Windows/Toolbox import and processor hardware behavior.

If an organization operates a self-hosted Windows runner with a licensed
toolchain, protect it as production infrastructure. Do not expose SDK files,
signing services, credentials, or generated customer packages to untrusted
pull requests. Require trusted-branch approval before a signing job.
