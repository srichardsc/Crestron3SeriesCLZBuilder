# Security policy

## Supported versions

Only the latest default branch is guaranteed to receive security fixes. Use a
tagged release when you need a stable build and record its source revision.

## Reporting a vulnerability

Please do not open a public issue for an undisclosed vulnerability, secret,
customer package, signing weakness, or exploitable proof of concept. Use a
private GitHub Security Advisory for
[`srichardsc/Crestron3SeriesCLZBuilder`](https://github.com/srichardsc/Crestron3SeriesCLZBuilder/security/advisories/new)
when available. If that channel is unavailable, contact the repository
maintainer privately before disclosure.

Include the affected revision, impact, minimal reproduction without secrets,
and a proposed mitigation if known. Redact credentials, private keys, PSKs,
customer hostnames, firmware dumps, and proprietary SDK files.

The project never needs a private signing key in source control. Report any
request for one, any attempt to bypass official assembly verification, or any
path that causes proprietary SDK binaries to be copied into artifacts or the
repository as a security issue.
