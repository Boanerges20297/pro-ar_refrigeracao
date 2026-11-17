# deploy_vps.ps1
# Deploy revisado: publica somente a main testada, sem mutacoes de banco.
param([switch]$PreflightOnly)

$ErrorActionPreference = 'Stop'
$IP = '76.13.237.243'
$SSH_USER = 'root'
$REMOTE_PATH = '/var/www/pro-ar_refrigeracao'

# Executar sempre na raiz deste repositorio, independente do terminal.
Set-Location $PSScriptRoot

Write-Host 'DEPLOY PRONTO-AR - verificacao do commit aprovado' -ForegroundColor Cyan
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') {
    throw 'Deploy bloqueado: execute a partir da branch main.'
}

$tracked = & git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $tracked) {
    throw 'Deploy bloqueado: existem alteracoes rastreadas no STI. Revise e concilie primeiro.'
}

& git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar origin/main.' }
$approvedSha = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel obter o commit local.' }
$originSha = (& git rev-parse origin/main).Trim()
if ($LASTEXITCODE -ne 0 -or $approvedSha -ne $originSha) {
    throw 'Deploy bloqueado: main local difere da main remota. Concilie antes.'
}
Write-Host "Commit revisado: $approvedSha" -ForegroundColor Green

if ($PreflightOnly) {
    Write-Host 'Preflight local aprovado. Nenhum push ou comando remoto executado.'
    return
}

# Nao realizar git add -A, commit automatico, nem editar URLs com token.
& git push origin main
if ($LASTEXITCODE -ne 0) { throw 'Push da main falhou; nenhuma atualizacao na VPS.' }

# Pipeline para ATUALIZACAO DE CODIGO. Migrações e finance sync exigem
# fluxo separado, backup e aprovacao especifica: nao rodar automaticamente.
$remoteCommands = @'
set -eu
# Git deve criar código legível pelo usuário do Gunicorn; jamais alterar .env/keys.
umask 022
cd /var/www/pro-ar_refrigeracao
test "$(git rev-parse --abbrev-ref HEAD)" = main
git diff --quiet HEAD
test "$(redis-cli -h 127.0.0.1 ping)" = PONG
grep -qx 'RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0' .env
.venv/bin/python -c 'import redis; import flask_limiter'
.venv/bin/pip check
git fetch origin main
test "$(git rev-parse origin/main)" = __APPROVED_SHA__
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = __APPROVED_SHA__
# Detecta arquivos de código sem leitura para www-data ANTES do restart.
runuser -u www-data -- .venv/bin/python -c 'import os; from pathlib import Path; assert all(os.access(p, os.R_OK) for p in Path("app").rglob("*.py")), "Código ilegível pelo Gunicorn"'
systemctl restart pro-ar
systemctl is-active --quiet pro-ar
curl -fsS -o /dev/null --max-time 12 --retry 3 --retry-delay 2 https://www.prontoar-servicos.com.br/auth/login
systemctl status pro-ar --no-pager
'@
$remoteCommands = ($remoteCommands -replace '\r', '').Replace('__APPROVED_SHA__', $approvedSha)

Write-Host 'Atualizando VPS pelo commit verificado. A senha SSH podera ser solicitada.' -ForegroundColor Yellow
& ssh -o PreferredAuthentications=password "$SSH_USER@$IP" $remoteCommands
if ($LASTEXITCODE -ne 0) {
    throw 'Deploy remoto falhou. Consulte logs e NAO repita sem diagnosticar.'
}
Write-Host "Deploy verificado: $approvedSha" -ForegroundColor Green
