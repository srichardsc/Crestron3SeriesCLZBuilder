# One-command driver build: auto-configures, bumps the version so Crestron
# Home accepts the package as an update, compiles, signs and publishes.
#
# Usage (from any folder containing a SIMPL# .csproj):
#   .\path\to\Run.ps1                       # first run creates the config
#   .\path\to\Run.ps1                       # every later run: new version + CLZ
#
# Optional:
#   -Project Project\Driver.csproj     explicit project when several exist
#   -Module SIMPL\Bridge.usp           repeatable; used only on first run
#   -Name Driver                       assembly filename stem; only on first run
#   -Configuration Release|Debug       default Release
#   -Targets series3,series4           default: both from the config
#   -VerifyReproducible                double-build byte-identity gate
#   -NoBump                            keep the existing version
#
# Keep this script compatible with Windows PowerShell 5.1.

[CmdletBinding()]
param(
    [Parameter()]
    [string] $Project,

    [Parameter()]
    [string[]] $Module,

    [Parameter()]
    [string] $Name,

    [Parameter()]
    [string] $Config = 'clz-builder.json',

    [Parameter()]
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',

    [Parameter()]
    [string] $Targets,

    [Parameter()]
    [switch] $VerifyReproducible,

    [Parameter()]
    [switch] $NoBump,

    [Parameter()]
    [string] $BuilderRoot,

    [Parameter()]
    [string] $Python
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'The SIMPL# / SPlusCC build requires Windows.'
}

if (-not $BuilderRoot) {
    # Default: this script lives in the builder repository's scripts folder.
    $BuilderRoot = Split-Path -Parent $PSScriptRoot
}
$builderRootPath = (Resolve-Path -LiteralPath $BuilderRoot).Path

$venvPython = Join-Path $builderRootPath '.venv\Scripts\python.exe'
$frozenExe = Join-Path $builderRootPath 'dist-exe\clz-builder.exe'
$pythonPath = $null
$mode = $null

if ($Python) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python executable not found: $Python" }
    $pythonPath = (Resolve-Path -LiteralPath $Python).Path
    $mode = 'module'
}
elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonPath = $venvPython
    $mode = 'module'
}
elseif (Test-Path -LiteralPath $frozenExe -PathType Leaf) {
    $pythonPath = $frozenExe
    $mode = 'entrypoint'
}
else {
    throw "Builder runtime not found. Run scripts\Setup.ps1 in $builderRootPath, or pass -BuilderRoot / -Python."
}

$cliArgs = @('run', '--config', $Config, '--configuration', $Configuration)
if ($Project) { $cliArgs += @('--project', $Project) }
foreach ($module in @($Module)) { if ($module) { $cliArgs += @('--module', $module) } }
if ($Name) { $cliArgs += @('--name', $Name) }
if ($Targets) { $cliArgs += @('--targets', $Targets) }
if ($VerifyReproducible) { $cliArgs += '--verify-reproducible' }
if ($NoBump) { $cliArgs += '--no-bump' }

if ($mode -eq 'module') {
    $sourceRoot = Join-Path $builderRootPath 'src'
    if (Test-Path -LiteralPath $sourceRoot -PathType Container) {
        if ($env:PYTHONPATH) { $env:PYTHONPATH = "$sourceRoot;$env:PYTHONPATH" } else { $env:PYTHONPATH = $sourceRoot }
    }
    & $pythonPath '-m' 'crestron_clz_builder' @cliArgs
}
else {
    & $pythonPath @cliArgs
}

exit $LASTEXITCODE
