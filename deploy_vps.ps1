# deploy_vps.ps1
# Script de deploy automatizado para Pronto Ar Refrigeração

# Configurações
$IP = "76.13.237.243"
$USER = "root"
$REMOTE_PATH = "/var/www/pro-ar_refrigeracao" # Ajuste se o caminho for outro (ex: /root/pro-ar_refrigeracao)
$SERVICE_NAME = "pro-ar"

# Carregar Token do GitHub do .env
$GITHUB_TOKEN = ""
if (Test-Path ".env") {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^GITHUB_TOKEN=(.*)$") {
            $GITHUB_TOKEN = $Matches[1].Trim()
        }
    }
}

Clear-Host
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   DEPLOY AUTOMATIZADO - PRONTO AR" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Enviar para GitHub
Write-Host "[1/3] Passo 1: Enviando alterações para o GitHub..." -ForegroundColor Yellow
git add -A
$commitMsg = "Deploy automático em $(Get-Date -Format 'dd/MM/yyyy HH:mm')"
git commit -m $commitMsg
git push origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao realizar o push para o GitHub. Verifique sua conexão e tente novamente." -ForegroundColor Red
    exit
}

Write-Host "Enviado com sucesso!" -ForegroundColor Green
Write-Host ""

# 2. Executar comandos na VPS via SSH
Write-Host "[2/3] Passo 2: Conectando à VPS ($IP)..." -ForegroundColor Yellow
Write-Host "DICA: A senha da sua VPS será solicitada pelo terminal." -ForegroundColor Gray

# Bloco de comandos remotos
$SET_REMOTE_URL = ""
if (-not [string]::IsNullOrEmpty($GITHUB_TOKEN)) {
    $SET_REMOTE_URL = "git remote set-url origin https://$GITHUB_TOKEN@github.com/Boanerges20297/pro-ar_refrigeracao.git && "
}
$REMOTE_COMMANDS = "cd $REMOTE_PATH && echo '--- Atualizando código ---' && ${SET_REMOTE_URL}git pull origin main && echo '--- Aplicando Migrations ---' && .venv/bin/flask db upgrade && echo '--- Sincronizando dados ---' && .venv/bin/flask finance sync && echo '--- Reiniciando o Servidor ---' && systemctl restart $SERVICE_NAME && systemctl status $SERVICE_NAME --no-pager"

ssh -o PreferredAuthentications=password "${USER}@${IP}" "$REMOTE_COMMANDS"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERRO: Falha ao executar comandos na VPS. Verifique a senha ou o caminho da pasta." -ForegroundColor Red
} else {
    Write-Host ""
    Write-Host "[3/3] Deploy finalizado com sucesso!" -ForegroundColor Green
    Write-Host "Acesse o sistema para verificar as mudanças." -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
