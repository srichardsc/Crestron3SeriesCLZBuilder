# Installation and dependencies

The supported build host is Windows with Windows PowerShell 5.1 or PowerShell
7. The legacy CF and Crestron tools are Windows-only. The repository's
PowerShell scripts are intentionally compatible with Windows PowerShell 5.1,
which is commonly available on commissioning laptops.

## Public prerequisites

Install Git, Python 3.10 or newer, and Visual Studio 2022 (Community,
Professional, Enterprise, or Build Tools with MSBuild). Use the official
[Visual Studio Community download](https://visualstudio.microsoft.com/vs/community/).
If the current download page offers a newer major version, use Microsoft's
[older Visual Studio downloads](https://visualstudio.microsoft.com/vs/older-downloads/)
page to select VS2022. Python is used for the generic build pipeline; MSBuild
compiles the selected `csproj`.

The optional commands below use the public `winget` catalog:

```powershell
.\scripts\Setup.ps1 -InstallOpenSource
.\scripts\Setup.ps1 -InstallBuildTools
```

`-InstallOpenSource` requests Python 3.12. `-InstallBuildTools` requests the
Microsoft VS2022 Build Tools MSBuild workload. Both are explicit opt-in
operations. Review winget output and local policy before accepting them.
Creating the local virtual environment also performs an editable `pip`
installation of this repository. The Python package has no runtime
dependencies, but pip may resolve the declared public setuptools build backend
from its configured package index when it is not already cached.

The public Windows **.NET Framework 3.5** feature can be enabled explicitly.
Microsoft also provides the [official .NET Framework 3.5 SP1
download](https://www.microsoft.com/es-es/download/details.aspx?id=21):

```powershell
# Run from an elevated PowerShell window.
.\scripts\Setup.ps1 -EnableNetFx3
```

This feature is not the **.NET Compact Framework 3.5** reference pack required
by the SIMPL# project. The Compact Framework is legacy and must be obtained
through the supported Microsoft/Crestron installation path for the selected
toolchain. This repository does not fetch or redistribute it.

## Proprietary prerequisites

Downloading Crestron software requires an authorized Crestron dealer account.
Obtain the versions licensed and supported by your organization through the
Crestron dealer channel. This includes SIMPL Windows, SIMPL+, SIMPL# SDK,
Cresdb, firmware tools, and the related signing/service components. This
repository does not provide download links, licenses, installers, or copied
vendor binaries.

Install the following components on the licensed Windows build host:

1. SIMPL Windows, including `SPlusCC.exe`, Crestron's SIMPL+ compiler.
2. The matching SIMPL# SDK and `SIMPLSharpService` assemblies.
3. Cresdb Programming data, including Required References and Required Project
   Files.
4. .NET Compact Framework 3.5 reference assemblies and compiler integration.

The checker looks for the following standard locations under
`%ProgramFiles(x86)%\Crestron` and `%WINDIR%`:

| Input | Typical location | Why it matters |
| --- | --- | --- |
| `SPlusCC.exe` | `Crestron\Simpl` | Crestron's SIMPL+ compiler; compiles target-specific `.usp` modules |
| `CSharpCompiler.dll` | `Crestron\Simpl` | SIMPL# compilation integration |
| `Crestron.Tools.SIMPLSharp.Services.dll` | `Crestron\Simpl` | official assembly verification/signing API |
| `Mono.Cecil.dll`, `Ionic.Zip.dll` | `Crestron\Simpl` | assembly and CLZ processing used by the pipeline |
| `csc.exe` CF 3.5 | `Microsoft.NET\Framework\v3.5` | Compact Framework compile step |
| CF reference assemblies | `Microsoft.NET\SDK\CompactFramework\v3.5\WindowsCE` | target references |
| Required References | `Crestron\Cresdb\Programming\Libraries\Required References` | SDK interfaces and metadata |
| Required Project Files | `Crestron\Cresdb\Programming\Libraries\Required Project Files` | SDK data resources |

Do not copy any of these files into this repository. If your installation is
non-standard, put approved absolute paths in the local `toolchain.paths`
object while diagnosing that host, or use environment-expanded values as
supported by the config schema. Keep those machine-specific edits local; do
not commit them.

When `-Config` is supplied, setup runs the package `doctor`; the core discovers
the host and refreshes the ignored local cache at
`.clz-builder/toolchain.local.json`. This fixed location prevents a project
configuration from redirecting local-state writes onto source files. The cache
contains absolute paths for this machine only; it is
revalidated by the CLI and must never be committed or copied between hosts.

## Verify a host

```powershell
.\scripts\Test-Toolchain.ps1
.\scripts\Test-Toolchain.ps1 -Json > toolchain-report.json
.\.venv\Scripts\python.exe -m crestron_clz_builder doctor --config .\clz-builder.json
```

`doctor` prints every input with its status; missing entries include the
expected path and an actionable fix, grouped into public versus licensed
components. Add `--json` for the machine-readable report used by scripts.
The interactive `setup` subcommand runs this check as part of a guided first
run and writes the lock when everything is present.

Exit code `0` means every required input was found. Exit code `2` means the
report is useful but one or more inputs are missing. Missing proprietary
entries are installation/licensing work. Do not download binaries from an
untrusted source; use the authorized Crestron dealer channel.

## PowerShell execution policy

Use a process-scoped policy change when local policy blocks a checked-out
script. Do not change machine policy just to run this repository:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

The scripts do not require administrator rights unless `-EnableNetFx3` is
used. Installing VS Build Tools or proprietary software may require separate
installer elevation.

## First build

Create/select a project configuration, then run:

```powershell
.\scripts\Build.ps1 `
  -Config .\clz-builder.json
```

The exact configuration schema and output contract are described in
[`BUILD.md`](BUILD.md). Run `Build.ps1 -?` for the current wrapper parameters.
