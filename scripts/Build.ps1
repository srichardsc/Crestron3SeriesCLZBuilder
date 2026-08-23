[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $Config,

    [Parameter()]
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',

    [Parameter()]
    [string] $Targets,

    [Parameter()]
    [switch] $VerifyReproducible,

    [Parameter()]
    [switch] $NoPublish,

    [Parameter()]
    [switch] $RecoverLock,

    [Parameter()]
    [string] $Python,

    [Parameter()]
    [switch] $SkipDoctor
)

# Keep this wrapper compatible with Windows PowerShell 5.1, which is still
# present on many Crestron build hosts.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$isWindowsHost = $env:OS -eq 'Windows_NT'
if (-not $isWindowsHost) {
    throw 'The SIMPL# / SPlusCC build requires Windows.'
}

$root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$configCandidate = if ([System.IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $root $Config }
if (-not (Test-Path -LiteralPath $configCandidate -PathType Leaf)) {
    throw "Configuration file not found: $configCandidate"
}
$configPath = (Resolve-Path -LiteralPath $configCandidate).Path

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$pythonPath = $null
$pythonPrefix = @()
$pythonMode = $null
if ($Python) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Python executable not found: $Python"
    }
    $pythonPath = (Resolve-Path -LiteralPath $Python).Path
    $pythonMode = 'module'
}
elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonPath = (Resolve-Path -LiteralPath $venvPython).Path
    $pythonMode = 'module'
}
else {
    $installed = Get-Command crestron-clz.exe -ErrorAction SilentlyContinue
    if (-not $installed) { $installed = Get-Command crestron-clz -ErrorAction SilentlyContinue }
    if ($installed) {
        $pythonPath = $installed.Source
        $pythonMode = 'entrypoint'
    }
    else {
        $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pyCommand) {
            $pythonPath = $pyCommand.Source
            $pythonPrefix = @('-3')
            $pythonMode = 'module'
        }
        elseif ($pythonCommand) {
            $pythonPath = $pythonCommand.Source
            $pythonMode = 'module'
        }
        else {
            throw 'Python 3 not found. Run .\scripts\Setup.ps1 -InstallOpenSource.'
        }
    }
}

if ($pythonMode -eq 'module') {
    $sourceRoot = Join-Path $root 'src'
    if (Test-Path -LiteralPath $sourceRoot -PathType Container) {
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = $sourceRoot + ';' + $env:PYTHONPATH
        }
        else {
            $env:PYTHONPATH = $sourceRoot
        }
    }
}

function Invoke-Clz {
    param([Parameter(Mandatory)] [string[]] $Arguments)

    if ($pythonMode -eq 'entrypoint') {
        & $pythonPath @Arguments | Out-Host
    }
    else {
        & $pythonPath @($pythonPrefix + @('-m', 'crestron_clz_builder') + $Arguments) | Out-Host
    }
    return $LASTEXITCODE
}

if (-not $SkipDoctor) {
    Write-Host 'Running project/toolchain doctor...'
    $doctorExit = Invoke-Clz -Arguments @('doctor', '--config', $configPath)
    if ($doctorExit -ne 0) {
        throw "Doctor failed with exit code $doctorExit. Install/configure the entries reported above."
    }
}

$buildArgs = @('build', '--config', $configPath, '--configuration', $Configuration)
if ($Targets) { $buildArgs += @('--targets', $Targets) }
if ($VerifyReproducible) { $buildArgs += '--verify-reproducible' }
if ($NoPublish) { $buildArgs += '--no-publish' }
if ($RecoverLock) { $buildArgs += '--recover-lock' }

Write-Host 'Running generic CLZ build pipeline.'
$buildExit = Invoke-Clz -Arguments $buildArgs
if ($buildExit -ne 0) {
    throw "Build failed with exit code $buildExit. See the first failing tool output above."
}
