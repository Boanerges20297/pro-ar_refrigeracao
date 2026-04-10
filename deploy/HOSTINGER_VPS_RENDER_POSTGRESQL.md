# Arquitetura Final: Hostinger VPS + Render + PostgreSQL

Este documento prepara a arquitetura fechada com o cliente:

- app principal na Hostinger VPS;
- banco PostgreSQL do app principal na Hostinger;
- `license_api` hospedada no Render;
- banco PostgreSQL separado para a `license_api`.

O fluxo comercial continua manual: a equipe cria e administra a licença no painel do `license_api`, e o cliente ativa a chave no sistema principal.

## 1. Desenho final

### App principal

- Hospedagem: Hostinger VPS
- Runtime: Gunicorn + Nginx
- Banco: PostgreSQL
- Persistência local: uploads, QR codes, installation id

### License API

- Hospedagem: Render Web Service
- Runtime: Uvicorn/FastAPI
- Banco: PostgreSQL do Render ou PostgreSQL externo dedicado
- Painel administrativo: `/admin`

## 2. O que ficou pronto no código

- o app principal agora aceita `DATABASE_URL` PostgreSQL com normalização automática de `postgres://`;
- o `license_api` também aceita `LICENSE_API_DATABASE_URL` PostgreSQL com o mesmo tratamento;
- o app principal aceita `LICENSE_PUBLIC_KEY_PEM` para validar licenças sem depender de arquivo local;
- o `license_api` aceita `LICENSE_PRIVATE_KEY_PEM` e `LICENSE_PUBLIC_KEY_PEM`, ideal para o Render;
- o `license_api` ganhou trilha de migration via Alembic em `license_api/migrations/`;
- o `license_api` permite desligar `create_all` automático com `LICENSE_API_AUTO_CREATE_SCHEMA=false`.

## 3. Banco PostgreSQL do app principal

Na VPS da Hostinger, crie:

- banco: `pro_ar_refrigeracao`
- usuário dedicado com senha forte
- permissões do usuário apenas nesse banco

Variáveis recomendadas no `.env` do app principal:

```env
SECRET_KEY=gere-um-valor-forte
JWT_SECRET_KEY=gere-outro-valor-forte
DATABASE_URL=postgresql+psycopg://pro_ar_user:SENHA@127.0.0.1:5432/pro_ar_refrigeracao
DATABASE_SSLMODE=prefer
DATABASE_POOL_RECYCLE_SECONDS=1800
UPLOAD_ROOT=/var/www/pro-ar_refrigeracao/uploads
PREFERRED_URL_SCHEME=https
JWT_COOKIE_SECURE=true
SESSION_COOKIE_SECURE=true
PROXY_FIX_ENABLED=true
PROXY_FIX_X_FOR=1
PROXY_FIX_X_PROTO=1
PROXY_FIX_X_HOST=1
PROXY_FIX_X_PORT=1
TRUSTED_HOSTS=app.seudominio.com
LICENSE_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
LICENSE_ALLOW_LEGACY_TOKENS=false
```

## 4. Migration do app principal para PostgreSQL

O app principal já possui migrations em `migrations/`.

Na VPS:

```bash
source .venv/bin/activate
flask db upgrade
```

Se você precisar migrar dados já existentes do SQLite de desenvolvimento, a recomendação prática é:

1. congelar o banco SQLite atual;
2. subir o schema no PostgreSQL com `flask db upgrade`;
3. importar dados manualmente ou via ferramenta dedicada como `pgloader`.

Para ambiente novo de cliente, basta subir o schema direto no PostgreSQL e depois usar o seed inicial, se necessário.

## 5. Banco PostgreSQL da license_api

No Render, use um PostgreSQL separado da aplicação principal.

Variáveis recomendadas para o serviço Render:

```env
LICENSE_API_NAME=BTA License API
LICENSE_API_TOKEN=gere-um-token-forte
LICENSE_API_DATABASE_URL=postgresql+psycopg://license_user:SENHA@HOST:5432/license_api
LICENSE_API_DATABASE_SSLMODE=require
LICENSE_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
LICENSE_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
LICENSE_ALLOW_PERPETUAL=true
LICENSE_API_AUTO_CREATE_SCHEMA=false
```

## 6. Migration da license_api para PostgreSQL

Agora a `license_api` possui migration própria.

Comandos:

```bash
source .venv/bin/activate
pip install -r license_api/requirements.txt
alembic -c license_api/alembic.ini upgrade head
```

Se quiser gerar futuras revisões:

```bash
alembic -c license_api/alembic.ini revision --autogenerate -m "descricao"
```

## 7. Chaves no Render e validação na VPS

Como o cliente ainda vai entrar em contato e a chave será criada manualmente no painel do `license_api`, o fluxo recomendado é:

1. publicar o `license_api` no Render com `LICENSE_PRIVATE_KEY_PEM` e `LICENSE_PUBLIC_KEY_PEM` fixos;
2. acessar o painel `/admin` do `license_api`;
3. emitir a licença manualmente para a empresa quando o cliente enviar os dados;
4. copiar a chave pública para o `.env` da VPS em `LICENSE_PUBLIC_KEY_PEM`;
5. entregar a chave de licença ao cliente para ativação no painel do app principal.

Importante:

- a chave privada nunca deve ficar na VPS do cliente;
- a VPS do cliente precisa apenas da chave pública.

## 8. Start commands sugeridos

### Hostinger VPS

```bash
gunicorn -c gunicorn.conf.py wsgi:app
```

### Render

```bash
uvicorn license_api.main:app --host 0.0.0.0 --port $PORT
```

## 9. Checklist operacional

- criar PostgreSQL do app principal na Hostinger;
- ajustar `.env` da VPS para PostgreSQL;
- rodar `flask db upgrade` na VPS;
- criar PostgreSQL da `license_api` no Render;
- configurar PEMs da `license_api` por variáveis de ambiente;
- rodar `alembic -c license_api/alembic.ini upgrade head` no ambiente da `license_api`;
- copiar a chave pública para `LICENSE_PUBLIC_KEY_PEM` na VPS;
- validar emissão manual de licença no painel `/admin`.