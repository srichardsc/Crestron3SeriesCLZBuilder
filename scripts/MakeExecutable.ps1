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
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Local environment not found: $venvPython. Run .\scripts\Setup.ps1 first."
}

if ($InstallPyInstaller -or -not (& $venvPython '-m' 'PyInstaller' '--version' 2>$null)) {
    Write-Host 'Installing PyInstaller into the local .venv...'
    & $venvPython '-m' 'pip' 'install' 'pyinstaller>=6.0'
    if ($LASTEXITCODE -ne 0) { throw 'pip install pyinstaller failed.' }
}

$outputDir = Join-Path $root 'dist-exe'
$buildDir = Join-Path $root 'build-exe'
$name = 'clz-builder'

Write-Host 'Building single-file executable...'
& $venvPython '-m' 'PyInstaller' `
    '--clean' `
    '--noconfirm' `
    '--onefile' `
    '--name', $name `
    '--distpath', $outputDir `
    '--workpath', $buildDir `
    '--specpath', $buildDir `
    '--add-data', "$(Join-Path $root 'src\crestron_clz_builder\Signer.cs');crestron_clz_builder" `
    '--hidden-import', 'crestron_clz_builder' `
    (Join-Path $root 'src\crestron_clz_builder\__main__.py')
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
