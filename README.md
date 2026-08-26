# Crestron3SeriesCLZBuilder

Open-source tooling and documentation for building Crestron `CLZ` packages
from a selectable project configuration, a `SIMPL#` project, its assembly, and
zero or more `SIMPL+` (`.usp`) modules. The same `CLZ` can be installed on
3-Series and 4-Series; the 3-Series target describes the historical build flow
and does not, by itself, limit the compatible processor.

This repository is generic rather than tied to one product. A configuration
selects the `csproj`, assembly name, `.usp` modules, targets (`series3`,
`series4`), output directory, and reproducibility options. Users choose these
values with `--config` or the equivalent `scripts/Build.ps1` parameters.

The final build uses proprietary tools and resources installed on the build
machine:
**VS2022/MSBuild**, **.NET Compact Framework 3.5**, **SIMPL Windows**, **SPlusCC
(Crestron's SIMPL+ compiler)**, **Cresdb**, and the **SIMPL# SDK /
SIMPLSharpService**. This repository does not
download, copy, redistribute, or recreate those components. It contains no
certificates, private keys, example PSKs, or homemade signer.

## Quick start

On a Windows development machine:

```powershell
git clone https://github.com/srichardsc/Crestron3SeriesCLZBuilder.git
Set-Location .\Crestron3SeriesCLZBuilder
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Create an isolated .venv, install this local package, and inspect the host.
# The script does not install or modify the Crestron SDK.
.\scripts\Setup.ps1

# Guided setup: finds your project, checks all 24 toolchain inputs, prints
# the exact fix for every missing component, then prepares config + lock.
.\.venv\Scripts\python.exe -m crestron_clz_builder setup

# Build selected targets and output defined by that configuration.
.\scripts\Build.ps1 -Config .\clz-builder.json

# Two clean builds and SHA-256 comparison before publication.
.\scripts\Build.ps1 -Config .\clz-builder.json -VerifyReproducible
```

Never used this kind of tool before? Follow [`docs/FOR-DUMMIES.md`](docs/FOR-DUMMIES.md)
instead: it explains every step from clone to SIMPL Windows import. Prefer no
Python on the build machine? Generate a single-file executable with
`.\scripts\MakeExecutable.ps1` and run `clz-builder.exe setup`.

Replace example names with the files in the selected project. If `Setup.ps1`
reports missing proprietary components, follow
[`docs/INSTALLATION.md`](docs/INSTALLATION.md). Downloading Crestron software,
SIMPL Windows, SIMPL+, SDKs, or related tools requires an authorized Crestron
dealer account. The script cannot accept a license, download, or install those
components on the user's behalf.

## What gets built

```text
selected config + SIMPL# source (.NET Compact Framework 3.5)
        + SIMPL+ modules + local Crestron toolchain
        ↓
MSBuild → SIMPL# assembly → official verification/signing
        ↓
deterministic CLZ + manifest + dependencies
        ↓
Crestron's SPlusCC SIMPL+ compiler per target → 3-Series / 4-Series .USH symbols
        ↓
selected output directory
```

The assembly and `CLZ` are built once and copied to selected targets. `.USH`
files are generated separately because Crestron's SIMPL+ compiler
(`SPlusCC.exe`) receives the target.
A successful build is not hardware acceptance. SIMPL Windows import, firmware,
Toolbox, reboot, and real operation still need to be checked on a processor.

## Requirements

| Component | Required for | Installation |
| --- | --- | --- |
| Windows 10/11 x64 | build and Crestron tools | supported development host |
| Git | clone and review changes | public; can be installed with winget |
| Python 3.10+ | reproducible pipeline | public; `Setup.ps1 -InstallOpenSource` can install it |
| Visual Studio 2022 / MSBuild 17.x | compile the project | [Visual Studio Community](https://visualstudio.microsoft.com/vs/community/) or [older Visual Studio downloads](https://visualstudio.microsoft.com/vs/older-downloads/) |
| .NET Framework 3.5 | public Windows feature/reference prerequisite | [Microsoft download](https://www.microsoft.com/es-es/download/details.aspx?id=21); this is not Compact Framework |
| .NET Compact Framework 3.5 | CF references and `csc.exe` | legacy/manual installation; not downloaded here |
| SIMPL Windows + SPlusCC (Crestron's SIMPL+ compiler) | generate `.USH` | local Crestron installation |
| Cresdb / Required References | data, interfaces, dependencies | local Crestron installation |
| SIMPL# SDK / SIMPLSharpService | compile/verify assembly | local Crestron installation |

Standard paths are autodetected. For a non-standard installation, keep approved
absolute paths in the local `toolchain.paths` configuration and let `doctor`
refresh `.clz-builder/toolchain.local.json`; see
[`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## Selectable configuration

The core defines the configuration file schema. The stable contract must be
able to represent at least:

```json
{
  "schema": 1,
  "assembly": {
    "project": "Project/Driver.csproj",
    "name": "Driver",
    "version": "1.0.0.0",
    "minimumFirmware": "1.007.0017"
  },
  "modules": ["SIMPL/Bridge.usp"],
  "targets": ["series3", "series4"],
  "package": { "dependencies": [], "resources": [], "metadata": {} },
  "toolchain": { "paths": {} },
  "output": { "build": "build", "dist": "dist" }
}
```

Relative paths resolve from the directory containing the configuration file.
The versioned lock is always `toolchain.lock.json`; discovered absolute paths
are always kept separately in ignored `.clz-builder/toolchain.local.json`.
Configuration must not
contain secrets, certificates, or paths that require copying SDK binaries.
For a one-off run, `Build.ps1` can override `-Configuration`, `-Targets`,
`-VerifyReproducible`, `-NoPublish`, and `-RecoverLock`. Project/module
selection is recorded by `init` in the configuration file.

## Documentation

- [First-time guide](docs/FOR-DUMMIES.md): zero-knowledge, step-by-step from clone to import in SIMPL Windows.
- [Installation and dependencies](docs/INSTALLATION.md): Windows,
  VS2022/MSBuild, CF 3.5, SIMPL Windows, SPlusCC (Crestron's SIMPL+ compiler),
  Cresdb, and SIMPL# SDK.
- [Build and packaging](docs/BUILD.md): `--config` selection, pipeline,
  options, outputs, and gates.
- [Driver development](docs/DRIVER-DEVELOPMENT.md): how to write a
  3-Series-compatible SIMPL# driver in VS2022, choose CF references, define the
  SIMPL+ boundary, and test on hardware.
- [Configuration reference](docs/CONFIGURATION.md): exact schema, path rules,
  assembly output templates, local discovery, and multi-project selection.
- [Reproducibility](docs/REPRODUCIBILITY.md): lockfile, hashes, staging, and
  deliberate toolchain updates.
- [Security and signing](docs/SECURITY.md): boundaries, secrets,
  certificates, and proprietary binary handling.
- [Troubleshooting](docs/TROUBLESHOOTING.md): common failures and evidence
  needed to escalate.
- [CI](docs/CI.md): what GitHub Actions can validate and what requires a host
  with Crestron installed.
- [Prior art and acknowledgements](docs/ACKNOWLEDGEMENTS.md): community
  research that informed the project.

## License and boundaries

Original code and documentation in this repository are released under MIT.
That license grants no rights to Crestron software, trademarks, SDK, firmware,
formats, or certificates. See [`LICENSE`](LICENSE) and
[`SECURITY.md`](SECURITY.md).

Contributions must preserve the separation between open-source code and the
proprietary toolchain. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
