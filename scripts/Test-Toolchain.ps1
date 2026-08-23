[CmdletBinding()]
param(
    [Parameter()]
    [string] $Root,

    [Parameter()]
    [switch] $Json

)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }

function Find-File {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string[]] $Candidates
    )

    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Find-CommandPath {
    param([Parameter(Mandatory)] [string[]] $Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source) {
            return $command.Source
        }
    }

    return $null
}

function Get-MsBuildCandidates {
    $programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    $result = [System.Collections.Generic.List[string]]::new()

    foreach ($base in @($programFilesX86, $programFiles)) {
        if (-not $base) { continue }
        foreach ($edition in @('Community', 'Professional', 'Enterprise', 'BuildTools')) {
            $result.Add((Join-Path $base "Microsoft Visual Studio\2022\$edition\MSBuild\Current\Bin\MSBuild.exe"))
        }
    }

    $vswhere = Find-File -Name 'vswhere.exe' -Candidates @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'),
        (Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\Installer\vswhere.exe')
    )
    if ($vswhere) {
        try {
            $installPath = & $vswhere -latest -products '*' -requires Microsoft.Component.MSBuild -property installationPath 2>$null
            if ($LASTEXITCODE -eq 0 -and $installPath) {
                $result.Add((Join-Path ([string] $installPath).Trim() 'MSBuild\Current\Bin\MSBuild.exe'))
            }
        }
        catch {
            # Fixed-path candidates remain useful when vswhere is unavailable.
        }
    }

    return $result.ToArray()
}

$isWindowsHost = $env:OS -eq 'Windows_NT'
if (-not $isWindowsHost) {
    throw 'El toolchain SIMPL# / SPlusCC requiere Windows; no se puede validar en este sistema.'
}

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
$programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
$windows = [Environment]::GetEnvironmentVariable('WINDIR')
$crestronRoot = if ($programFilesX86) { Join-Path $programFilesX86 'Crestron' } else { $null }
$simplRoot = if ($crestronRoot) { Join-Path $crestronRoot 'Simpl' } else { $null }
$cresdbRoot = if ($crestronRoot) { Join-Path $crestronRoot 'Cresdb\Programming' } else { $null }
$cfRoot = if ($programFilesX86) { Join-Path $programFilesX86 'Microsoft.NET\SDK\CompactFramework\v3.5\WindowsCE' } else { $null }

$python = Find-CommandPath -Names @('py.exe', 'python.exe', 'python')
$msbuild = Find-File -Name 'MSBuild.exe' -Candidates (Get-MsBuildCandidates)
$spluscc = Find-File -Name 'SPlusCC.exe' -Candidates @(
    $(if ($simplRoot) { Join-Path $simplRoot 'SPlusCC.exe' } else { $null })
)
$compiler = Find-File -Name 'CSharpCompiler.dll' -Candidates @(
    $(if ($simplRoot) { Join-Path $simplRoot 'CSharpCompiler.dll' } else { $null })
)
$services = Find-File -Name 'Crestron.Tools.SIMPLSharp.Services.dll' -Candidates @(
    $(if ($simplRoot) { Join-Path $simplRoot 'Crestron.Tools.SIMPLSharp.Services.dll' } else { $null })
)
$ionic = Find-File -Name 'Ionic.Zip.dll' -Candidates @(
    $(if ($simplRoot) { Join-Path $simplRoot 'Ionic.Zip.dll' } else { $null })
)
$cecil = Find-File -Name 'Mono.Cecil.dll' -Candidates @(
    $(if ($simplRoot) { Join-Path $simplRoot 'Mono.Cecil.dll' } else { $null })
)
$cfCsc = Find-File -Name 'csc.exe (CF 3.5)' -Candidates @(
    $(if ($windows) { Join-Path $windows 'Microsoft.NET\Framework\v3.5\csc.exe' } else { $null })
)
$cfMscorlib = Find-File -Name 'mscorlib.dll (CF 3.5)' -Candidates @(
    $(if ($cfRoot) { Join-Path $cfRoot 'mscorlib.dll' } else { $null })
)
$references = if ($cresdbRoot) { Join-Path $cresdbRoot 'Libraries\Required References' } else { $null }
$data = if ($cresdbRoot) { Join-Path $cresdbRoot 'Libraries\Required Project Files' } else { $null }

$items = @(
    [pscustomobject]@{ Name = 'Python'; Required = $true; Path = $python; Note = 'Python 3.10+ for the package CLI' },
    [pscustomobject]@{ Name = 'VS2022 MSBuild'; Required = $true; Path = $msbuild; Note = 'MSBuild 17.x' },
    [pscustomobject]@{ Name = 'CF 3.5 csc.exe'; Required = $true; Path = $cfCsc; Note = 'Microsoft .NET Compact Framework 3.5' },
    [pscustomobject]@{ Name = 'CF 3.5 mscorlib.dll'; Required = $true; Path = $cfMscorlib; Note = 'CF reference assembly' },
    [pscustomobject]@{ Name = 'SPlusCC.exe'; Required = $true; Path = $spluscc; Note = 'SIMPL Windows / SPlusCC' },
    [pscustomobject]@{ Name = 'CSharpCompiler.dll'; Required = $true; Path = $compiler; Note = 'SIMPL# SDK' },
    [pscustomobject]@{ Name = 'SIMPLSharp services'; Required = $true; Path = $services; Note = 'SIMPLSharpService verification API' },
    [pscustomobject]@{ Name = 'Mono.Cecil.dll'; Required = $true; Path = $cecil; Note = 'SDK assembly processing dependency' },
    [pscustomobject]@{ Name = 'Ionic.Zip.dll'; Required = $true; Path = $ionic; Note = 'SDK CLZ packaging dependency' },
    [pscustomobject]@{ Name = 'Cresdb Required References'; Required = $true; Path = $references; Note = 'Crestron reference assemblies'; },
    [pscustomobject]@{ Name = 'Cresdb Required Project Files'; Required = $true; Path = $data; Note = 'SimplSharpData resources'; }
)

$result = [pscustomobject]@{
    Root = $rootPath
    Windows = $isWindowsHost
    Items = @($items | ForEach-Object {
        [pscustomobject]@{
            Name = $_.Name
            Required = $_.Required
            Found = [bool]$_.Path -and (Test-Path -LiteralPath $_.Path)
            Path = $_.Path
            Note = $_.Note
        }
    })
}
$missing = @($result.Items | Where-Object { $_.Required -and -not $_.Found })

if ($Json) {
    $result | ConvertTo-Json -Depth 5
}
else {
    Write-Host "Crestron3SeriesCLZBuilder toolchain check: $rootPath"
    $result.Items | ForEach-Object {
        $state = if ($_.Found) { 'OK' } else { 'MISSING' }
        $color = if ($_.Found) { 'Green' } else { 'Yellow' }
        $displayPath = if ($_.Path) { $_.Path } else { $_.Note }
        Write-Host ("[{0,-7}] {1,-30} {2}" -f $state, $_.Name, $displayPath) -ForegroundColor $color
    }
    Write-Host ''
    if ($missing.Count -gt 0) {
        Write-Host 'Missing proprietary entries require a licensed local Crestron installation.' -ForegroundColor Yellow
        Write-Host 'No SDK binary, firmware, certificate or key is downloaded by this script.' -ForegroundColor Yellow
    }
    else {
        Write-Host 'All required toolchain inputs were found.' -ForegroundColor Green
    }
}

if ($missing.Count -gt 0) {
    exit 2
}

exit 0
