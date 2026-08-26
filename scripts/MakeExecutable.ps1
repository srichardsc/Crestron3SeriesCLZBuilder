# Build a single-file Windows executable for the CLZ builder CLI.
#
# The executable bundles the Python package (including Signer.cs as package
# data) so end users do not need a Python installation. It does NOT bundle any
# Crestron software: the official SDK, SIMPL Windows/SPlusCC and Cresdb must
# already be installed on the host, exactly like the source distribution.
#
# Usage:
#   .\scripts\MakeExecutable.ps1                 # build dist-exe\clz-builder.exe
#   .\scripts\MakeExecutable.ps1 -InstallPyInstaller   # also install PyInstaller first
#
# Keep this script compatible with Windows PowerShell 5.1.

[CmdletBinding()]
param(
    [Parameter()]
    [switch] $InstallPyInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'The executable target is Windows-only (same requirement as the toolchain).'
}

$root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$pyCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    # Preferred: the local environment created by Setup.ps1.
    $venvPython = (Resolve-Path -LiteralPath $venvPython).Path
}
elseif ($pyCommand) {
    # CI / global install: the package is importable from PATH's Python.
    Write-Host "Using Python from PATH: $($pyCommand.Source)"
    $venvPython = $pyCommand.Source
}
else {
    throw "No usable Python found. Run .\scripts\Setup.ps1 or put python.exe on PATH."
}

& $venvPython '-c' 'import crestron_clz_builder' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'crestron_clz_builder is not importable. Run .\scripts\Setup.ps1 first.'
}

if (-not (& $venvPython '-m' 'PyInstaller' '--version' 2>$null)) {
    Write-Host 'Installing PyInstaller into the active Python...'
    & $venvPython '-m' 'pip' 'install' 'pyinstaller>=6.0'
    if ($LASTEXITCODE -ne 0) { throw 'pip install pyinstaller failed.' }
}

$outputDir = Join-Path $root 'dist-exe'
$buildDir = Join-Path $root 'build-exe'
$name = 'clz-builder'
$signerSource = Join-Path $root 'src\crestron_clz_builder\Signer.cs'
# entry.py uses absolute imports; __main__.py's relative imports break when
# executed as a frozen top-level script.
$entryScript = Join-Path $root 'src\crestron_clz_builder\entry.py'

Write-Host 'Building single-file executable...'
# All paths passed to PyInstaller must be absolute: relative --add-data paths
# are resolved against the spec/workpath directory, not the current location.
# Arguments are passed as a single array so PowerShell never merges or quotes them.
$pyiArgs = @(
    '-m', 'PyInstaller',
    '--clean',
    '--noconfirm',
    '--onefile',
    '--name', $name,
    '--distpath', $outputDir,
    '--workpath', $buildDir,
    '--specpath', $buildDir,
    "--add-data=$signerSource;crestron_clz_builder",
    '--hidden-import', 'crestron_clz_builder',
    $entryScript
)
& $venvPython @pyiArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

$executable = Join-Path $outputDir "$name.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "expected executable was not produced: $executable"
}

Write-Host ''
Write-Host "Created: $executable"
& $executable --version
if ($LASTEXITCODE -ne 0) { throw 'smoke test failed: executable did not report its version.' }
Write-Host ''
Write-Host 'Copy clz-builder.exe next to your driver project and run:'
Write-Host '  clz-builder.exe setup'
Write-Host '  clz-builder.exe build --config clz-builder.json'
