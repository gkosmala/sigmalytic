$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoPath = "C:\Users\owner\Desktop\Claude\V2 project\sigmalytic-campaign"
Set-Location -LiteralPath $RepoPath
[System.IO.Directory]::SetCurrentDirectory($RepoPath)

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force -Path ".\reports\browser_regression" | Out-Null

$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = ".\reports\browser_regression\run_$RunId"
$RunLog = ".\reports\browser_regression\run_$RunId.log"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

py -m pip show playwright *> ".\reports\browser_regression\playwright_check_$RunId.log"
if ($LASTEXITCODE -ne 0) {
    py -m pip install playwright *>> ".\reports\browser_regression\playwright_check_$RunId.log"
}

py -m playwright install chromium *> ".\reports\browser_regression\chromium_check_$RunId.log"

py -B ".\tests\browser\sigmalytic_live_ui_smoke.py" --headed --output-dir $RunDir *> $RunLog
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "SUMMARY:"
Get-Content (Join-Path $RunDir "summary.txt")

Write-Host ""
Write-Host "RUN LOG:"
Write-Host $RunLog

Write-Host ""
Write-Host "RUN DIR:"
Write-Host $RunDir

exit $ExitCode