# Security and signing

This project builds software that can be imported into Crestron control
systems. Treat the build host, proprietary SDK, generated packages, and
credentials as security-sensitive.

## Security boundaries

- Source-controlled code and scripts are open source.
- SDK binaries, Cresdb data, firmware, certificates, and signer services are
  proprietary inputs and stay on the licensed build host.
- The repository never asks for or stores a private signing key.
- The official SDK verification/signing service is a required gate; a homemade
  signer or self-issued certificate is not equivalent.
- Configuration files must contain selectors and paths only, never PSKs,
  tokens, credentials, certificates, or customer network details.
- `.clz-builder/toolchain.local.json` is generated, ignored local state. It may
  contain absolute installation paths and must be revalidated locally, never
  committed or shared as a portable lock.

## Safe build practice

Use a dedicated, patched Windows build host. Review changes to PowerShell and
Python scripts before execution. Pin and review the toolchain lock. Keep
generated `.clz`, `.ush`, DLL, EXE, and diagnostic output outside commits.
Verify SHA-256 values before installing a package on a processor, and retain
the source revision, config, toolchain report, and hardware acceptance record.
MD5 fields inside the Crestron manifest are format compatibility metadata only;
never treat them as security evidence.

Do not run the build against an untrusted output path, customer-controlled
source, or a writable SDK directory. Do not put private keys in environment
variables, command history, CI logs, or issue attachments.

## Supply-chain rules

The setup script may install public dependencies only when explicitly asked.
It never downloads Crestron software, firmware, SDK resources, or signing
material. Downloading those components requires an authorized Crestron dealer
account. Obtain them through the dealer-supported channel and verify their
license and integrity independently.

The CI workflow deliberately does not claim to build a signed CLZ when the
proprietary toolchain is unavailable. A green CI job covers source/scripts and
repository checks, not signing or hardware operation.

## Reporting a vulnerability

Do not publish secrets, customer artifacts, or an exploitable proof of concept
in a public issue. Use a private GitHub Security Advisory for the repository
when available, or contact the maintainers through the repository owner before
disclosure. Include affected revision, impact, minimal reproduction without
secrets, and mitigation. See the root [`SECURITY.md`](../SECURITY.md).
