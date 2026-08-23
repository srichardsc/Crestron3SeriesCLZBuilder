[CmdletBinding()]
param(
    [Parameter()]
    [string] $Root,

    [Parameter()]
    [switch] $InstallOpenSource,

    [Parameter()]
    [switch] $InstallBuildTools,

    [Parameter()]
    [switch] $EnableNetFx3,

    [Parameter()]
    [string] $Config,

    [Parameter()]
    [switch] $RunBuild,

    [Parameter()]
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',

    [Parameter()]
    [string] $Targets,

    [Parameter()]
    [switch] $VerifyReproducible
)

# Keep this setup helper compatible with Windows PowerShell 5.1.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }

$isWindowsHost = $env:OS -eq 'Windows_NT'
if (-not $isWindowsHost) {
    throw 'This project requires Windows for the SIMPL# / SPlusCC toolchain.'
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-WingetInstall {
    param(
        [Parameter(Mandatory)] [string] $Id,
        [Parameter()] [string] $Override
    )

    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "winget is unavailable. Install $Id manually from its official source."
    }

    $wingetArgs = @(
        'install', '--id', $Id, '--exact', '--source', 'winget',
        '--accept-source-agreements', '--accept-package-agreements'
    )
    if ($Override) { $wingetArgs += @('--override', $Override) }
    Write-Host "Installing public dependency via winget: $Id"
    & winget @wingetArgs
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed for $Id (exit code $LASTEXITCODE)."
    }
}

function Get-PythonCommand {
    $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyCommand) { return @{ Path = $pyCommand.Source; Prefix = @('-3') } }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { return @{ Path = $pythonCommand.Source; Prefix = @() } }
    # winget may install Python without refreshing this process's PATH.
    $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
    $programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    foreach ($candidate in @(
        $(if ($localAppData) { Join-Path $localAppData 'Programs\Python\Python312\python.exe' } else { $null }),
        $(if ($programFiles) { Join-Path $programFiles 'Python312\python.exe' } else { $null }),
        $(if ($programFilesX86) { Join-Path $programFilesX86 'Python312\python.exe' } else { $null })
    )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return @{ Path = (Resolve-Path -LiteralPath $candidate).Path; Prefix = @() }
        }
    }
    return $null
}

$rootPath = (Resolve-Path -LiteralPath $Root).Path

if ($InstallOpenSource) {
    # Python is the public runtime required by the package CLI. Git normally
    # exists before clone and is intentionally not forced here.
    Invoke-WingetInstall -Id 'Python.Python.3.12'
}

if ($InstallBuildTools) {
    Invoke-WingetInstall -Id 'Microsoft.VisualStudio.2022.BuildTools' -Override '--wait --passive --add Microsoft.VisualStudio.Workload.MSBuildTools --includeRecommended'
}

if ($EnableNetFx3) {
    if (-not (Test-Administrator)) {
        throw '-EnableNetFx3 requires an elevated PowerShell window (Administrator).'
    }
    Write-Host 'Enabling the public Windows .NET Framework 3.5 feature...'
    Enable-WindowsOptionalFeature -Online -FeatureName NetFx3 -All -NoRestart | Out-Host
    Write-Host 'Note: NetFx3 is not the .NET Compact Framework 3.5 required by SIMPL#.' -ForegroundColor Yellow
}

$pythonInfo = Get-PythonCommand
$venvRoot = Join-Path $rootPath '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
if (-not $pythonInfo -and -not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host 'Python 3 is unavailable; install it or rerun with -InstallOpenSource.' -ForegroundColor Yellow
    exit 2
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host 'Creating local Python virtual environment: .venv'
    $venvArgs = @($pythonInfo.Prefix) + @('-m', 'venv', $venvRoot)
    & $pythonInfo.Path @venvArgs
    if ($LASTEXITCODE -ne 0) { throw "Python venv creation failed with exit code $LASTEXITCODE." }
}

Write-Host 'Installing this project into .venv (editable, no SDK files copied).'
& $venvPython '-m' 'pip' 'install' '--no-deps' '--editable' $rootPath
if ($LASTEXITCODE -ne 0) { throw "pip editable install failed with exit code $LASTEXITCODE." }

if ($Config) {
    $configCandidate = if ([System.IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $rootPath $Config }
    if (-not (Test-Path -LiteralPath $configCandidate -PathType Leaf)) {
        throw "Configuration file not found: $configCandidate"
    }
    $configPath = (Resolve-Path -LiteralPath $configCandidate).Path
    Write-Host 'Running project/toolchain doctor...'
    & $venvPython '-m' 'crestron_clz_builder' 'doctor' '--config' $configPath | Out-Host
    $doctorExit = $LASTEXITCODE
}
else {
    Write-Host 'No -Config supplied; checking standard toolchain paths.'
    & (Join-Path $PSScriptRoot 'Test-Toolchain.ps1') -Root $rootPath
    $doctorExit = $LASTEXITCODE
}

Write-Host ''
Write-Host 'Proprietary manual steps:' -ForegroundColor Yellow
Write-Host '  1. Install licensed SIMPL Windows/SPlusCC for the supported release.'
Write-Host '  2. Install the matching SIMPL# SDK / SIMPLSharpService and Cresdb.'
Write-Host '  3. Install or expose .NET Compact Framework 3.5 references.'
Write-Host '  4. Re-run Setup.ps1 with -Config until doctor reports the expected inputs.'

if ($RunBuild) {
    if (-not $Config) {
        throw '-RunBuild requires -Config <path> so project selection is explicit.'
    }
    if ($doctorExit -ne 0) {
        throw 'Build cannot run: doctor reported missing or invalid prerequisites.'
    }
    $buildArgs = @('-Config', $Config, '-Configuration', $Configuration)
    if ($Targets) { $buildArgs += @('-Targets', $Targets) }
    if ($VerifyReproducible) { $buildArgs += '-VerifyReproducible' }
    & (Join-Path $PSScriptRoot 'Build.ps1') @buildArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($doctorExit -ne 0) {
    Write-Host 'Setup completed with missing entries; see docs/INSTALLATION.md.' -ForegroundColor Yellow
    exit $doctorExit
}

Write-Host 'Setup/preflight completed successfully.' -ForegroundColor Green
exit 0
