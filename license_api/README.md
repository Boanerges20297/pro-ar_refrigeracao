# License API

API separada para emissao, verificacao e revogacao de licencas administradas pela BTA Solucoes em Desenvolvimento de Software.

Uso recomendado: backoffice interno para a equipe comercial/tecnica, nao painel do cliente final.

## Objetivo

Esta API existe fora do app Flask para resolver o problema do segredo compartilhado no cliente.
Ela emite a licenca com chave privada Ed25519 e o sistema do cliente deve validar apenas com a chave publica.

## O que esta implementado

- emissao de licenca perpetua ou por assinatura
- assinatura assimetrica Ed25519
- verificacao de assinatura e revogacao
- armazenamento local das licencas emitidas
- revogacao administrativa
- token administrativo simples por header `X-API-Token`
- painel web em `/admin` para emitir, listar e revogar licencas
- suporte a PostgreSQL por `LICENSE_API_DATABASE_URL`
- suporte a chaves PEM por variaveis de ambiente
- migrations proprias com Alembic em `license_api/migrations/`

## Estrutura

- `main.py`: endpoints FastAPI
- `service.py`: regras de negocio
- `security.py`: assinatura e verificacao
- `models.py`: tabela das licencas emitidas
- `migrations/`: migrations da API
- `keys/`: par de chaves gerado no primeiro startup
- `data/`: banco sqlite da API

## Instalar

```powershell
c:/Users/Boanerges/Desktop/Projetos/pro-ar_refrigeracao/.venv/Scripts/python.exe -m pip install -r license_api/requirements.txt
```

## Executar

```powershell
$env:LICENSE_API_TOKEN = "troque-isto"
c:/Users/Boanerges/Desktop/Projetos/pro-ar_refrigeracao/.venv/Scripts/python.exe -m uvicorn license_api.main:app --reload --port 8010
```

## Migrations

Para ambiente PostgreSQL, aplique o schema com Alembic:

```powershell
c:/Users/Boanerges/Desktop/Projetos/pro-ar_refrigeracao/.venv/Scripts/python.exe -m alembic -c license_api/alembic.ini upgrade head
```

Em producao, prefira desligar a criacao automatica de tabelas:

```env
LICENSE_API_AUTO_CREATE_SCHEMA=false
```

## Endpoints

### Painel web

```http
GET /admin/login
GET /admin
```

O painel permite:

- emitir licencas por plano `basic` ou `premium`
- listar licencas emitidas
- revogar licencas sem usar chamadas manuais de API

### Health

```http
GET /health
```

### Emitir licenca

```http
POST /licenses/issue
X-API-Token: troque-isto
Content-Type: application/json
```

Payload exemplo para licenca perpetua:

```json
{
  "company_name": "Cliente Exemplo Ltda.",
  "instance_fingerprint": "inst_abc123",
  "license_type": "perpetual",
  "status": "active",
  "max_users": 15,
  "max_admin_users": 2,
  "max_secretary_users": 3,
  "features": ["reports", "audit", "maintenance"]
}
```

Payload exemplo para assinatura:

```json
{
  "company_name": "Cliente Exemplo Ltda.",
  "instance_fingerprint": "inst_abc123",
  "license_type": "subscription",
  "duration_days": 365,
  "status": "active"
}
```

### Verificar licenca

```http
POST /licenses/verify
X-API-Token: troque-isto
Content-Type: application/json
```

```json
{
  "license_key": "TOKEN_AQUI",
  "expected_company_name": "Cliente Exemplo Ltda.",
  "expected_instance_fingerprint": "inst_abc123"
}
```

### Revogar licenca

```http
POST /licenses/{license_id}/revoke
X-API-Token: troque-isto
Content-Type: application/json
```

```json
{
  "reason": "inadimplencia ou troca autorizada de servidor"
}
```

## Integracao sugerida com o Flask atual

1. Remover a emissao local de licencas do Flask.
2. Manter no Flask apenas a validacao local com chave publica.
3. Trocar o fingerprint atual por um `installation_id` estavel gerado uma unica vez.
4. Fazer `inactive` bloquear a operacao, exceto login admin e tela de ativacao.
5. Criar suporte explicito a `license_type = perpetual` no avaliador do Flask.

## Planos sugeridos

### Basic

- operacao principal do sistema
- sem `reports`, `audit`, `maintenance`, `branding` e `email`

### Premium

- tudo do Basic
- `reports`
- `audit`
- `maintenance`
- `branding`
- `email`

## Modelo comercial recomendado

- o cliente final ativa e consulta a licenca no sistema principal;
- a `license_api` fica com a equipe responsavel por emissao, renovacao, upgrade e revogacao;
- detalhes comerciais completos, matriz de features e sugestoes de precificacao estao em `docs/LICENCIAMENTO_COMERCIAL.md`.

## Observacoes

- esta API ainda usa um token administrativo simples; para producao, o ideal e colocar HTTPS, rotacao de token e autentificacao mais forte
- a chave privada nunca deve ser distribuida para o cliente
- a chave publica pode ser embutida no app Flask por arquivo ou pela variavel `LICENSE_PUBLIC_KEY_PEM`
- no Render, prefira `LICENSE_PRIVATE_KEY_PEM` e `LICENSE_PUBLIC_KEY_PEM` para nao depender do filesystem efemero
