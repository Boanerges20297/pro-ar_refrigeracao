# Execute the complete isolated STI01 test suite. No deploy or production writes.
$ErrorActionPreference = 'Continue' # pytest stderr warnings must not abort exit-code handling
$env:PYTHONWARNINGS = 'ignore::ResourceWarning'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Crie .venv e instale requirements.txt e requirements-test.txt.' }
$reportDir = Join-Path $projectRoot 'tests\.results'
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$xml = Join-Path $reportDir 'junit.xml'
$coverageJson = Join-Path $reportDir 'coverage.json'
$log = Join-Path $reportDir 'pytest.log'
Write-Host 'Executando auditoria no STI01; sem acesso a bancos de producao.' -ForegroundColor Cyan
& $python -m pytest tests -q --disable-warnings --tb=short --cov=app --cov-branch --cov-report=term "--cov-report=json:$coverageJson" "--junitxml=$xml" *> $log
$exitCode = $LASTEXITCODE
Get-Content $log | Select-Object -Last 150
Write-Host "JUnit: $xml"
Write-Host "Cobertura: $coverageJson"
Write-Host "Log: $log"
exit $exitCode
