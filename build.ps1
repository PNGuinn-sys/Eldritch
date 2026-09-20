<#
.SYNOPSIS
  Builds the Windows release of Eldritch: Eldritch.exe plus data/ and the
  README, zipped as dist\Eldritch-<Version>-windows.zip.

.EXAMPLE
  .\build.ps1 -Version 0.3.0
  .\build.ps1 -Version 0.3.0 -SkipTests

.NOTES
  One-time setup:  pip install -r requirements-dev.txt
  Output goes to build\ and dist\ (both git-ignored). Prints SHA-256 hashes
  for the release notes. Publishing is a separate, manual step, e.g.:
    gh release create v0.3.0 dist\Eldritch-0.3.0-windows.zip --prerelease
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$')]
    [string]$Version,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Invoke-Checked {
    # Native commands don't stop the script on failure by themselves.
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

if (-not $SkipTests) {
    Write-Host "== Running tests ==" -ForegroundColor Cyan
    Invoke-Checked "Tests" { python tests/test_engine.py | Select-Object -Last 1 }
}

Write-Host "== Building Eldritch.exe ==" -ForegroundColor Cyan
$work = Join-Path $root 'build'
$out  = Join-Path $root 'dist'
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
if (Test-Path $out)  { Remove-Item -Recurse -Force $out }

# --add-data needs an ABSOLUTE source path (PyInstaller resolves relative
# ones against the spec directory, not the current one).
$data = (Resolve-Path (Join-Path $root 'data')).Path
Invoke-Checked "PyInstaller" {
    python -m PyInstaller --noconfirm --onefile --console --name Eldritch --log-level WARN `
        --add-data "${data};data" `
        --distpath "$work\pyinstaller" --workpath "$work\work" --specpath $work `
        main.py
}

Write-Host "== Assembling package ==" -ForegroundColor Cyan
$pkg = Join-Path $out 'Eldritch'
New-Item -ItemType Directory -Force $pkg | Out-Null
Copy-Item (Join-Path $work 'pyinstaller\Eldritch.exe') $pkg
Copy-Item (Join-Path $root 'README.md') $pkg
Copy-Item -Recurse $data (Join-Path $pkg 'data')
Get-ChildItem $pkg -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

$zip = Join-Path $out "Eldritch-$Version-windows.zip"
Compress-Archive -Path $pkg -DestinationPath $zip -Force

$exeHash = (Get-FileHash (Join-Path $pkg 'Eldritch.exe') -Algorithm SHA256).Hash
$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Built:  $zip  ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)" -ForegroundColor Green
Write-Host "Commit: $(git rev-parse --short HEAD)  (uncommitted changes: $((git status --porcelain | Measure-Object).Count))"
Write-Host "SHA-256 zip: $zipHash"
Write-Host "SHA-256 exe: $exeHash"
