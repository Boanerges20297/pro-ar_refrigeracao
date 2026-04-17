#!/bin/bash

# Script para configurar o Git remoto na VPS Hostinger
# Uso: bash scripts/setup_vps_git.sh

REPO_URL="https://github.com/Boanerges20297/pro-ar_refrigeracao.git"
GITHUB_TOKEN=$(cat github_token 2>/dev/null || echo "")

if [ -z "$GITHUB_TOKEN" ]; then
    echo "Erro: Arquivo github_token não encontrado ou vazio."
    echo "Certifique-se de que o arquivo github_token existe na raiz do projeto na VPS."
    exit 1
fi

# Formata a URL com o token para autenticação automática
AUTH_REPO_URL="https://${GITHUB_TOKEN}@github.com/Boanerges20297/pro-ar_refrigeracao.git"

echo "Configurando Git remoto para: $REPO_URL"

# Garante que o diretório é um repositório git
if [ ! -d ".git" ]; then
    echo "Inicializando repositório Git..."
    git init
fi

# Adiciona ou atualiza o remote 'origin'
if git remote | grep -q 'origin'; then
    echo "Atualizando remote 'origin' existente..."
    git remote set-url origin "$AUTH_REPO_URL"
else
    echo "Adicionando novo remote 'origin'..."
    git remote add origin "$AUTH_REPO_URL"
fi

# Configura o helper de credenciais para não pedir senha novamente
git config credential.helper store

# Define o nome da branch principal como main
git branch -M main

# Busca alterações do remoto
echo "Buscando alterações do GitHub..."
git fetch origin main

# Configura o upstream
git branch --set-upstream-to=origin/main main

echo "--------------------------------------------------"
echo "Configuração concluída!"
echo "Agora você pode atualizar a VPS com: git pull"
echo "--------------------------------------------------"
