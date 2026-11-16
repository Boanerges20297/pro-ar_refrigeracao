# Deploy detalhado na Hostinger VPS

Este guia prepara o projeto para rodar em uma VPS Linux com Gunicorn + Nginx.

## 1. Premissas

- VPS Linux Ubuntu 22.04 ou 24.04
- acesso root ou usuario com sudo
- dominio apontado para o IP da VPS
- repositorio do projeto disponivel por Git ou upload manual

## 2. Pacotes do sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

## 3. Estrutura sugerida

```bash
sudo mkdir -p /var/www/pro-ar_refrigeracao
sudo chown -R $USER:$USER /var/www/pro-ar_refrigeracao
cd /var/www/pro-ar_refrigeracao
```

## 4. Publicar o codigo

Opcao Git:

```bash
git clone <SEU_REPOSITORIO> .
```

Opcao upload manual:

- envie os arquivos do projeto para `/var/www/pro-ar_refrigeracao`

## 5. Criar ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Configurar ambiente

Use o arquivo `.env.example` como base:

```bash
cp .env.example .env
nano .env
```

Valores recomendados para testes na VPS:

```env
SECRET_KEY=gere-um-valor-forte
JWT_SECRET_KEY=gere-outro-valor-forte
DATABASE_URL=sqlite:////var/www/pro-ar_refrigeracao/instance/pronto_ar.db
UPLOAD_ROOT=/var/www/pro-ar_refrigeracao/uploads
PREFERRED_URL_SCHEME=https
JWT_COOKIE_SECURE=true
SESSION_COOKIE_SECURE=true
PROXY_FIX_ENABLED=true
PROXY_FIX_X_FOR=1
PROXY_FIX_X_PROTO=1
PROXY_FIX_X_HOST=1
PROXY_FIX_X_PORT=1
SERVER_NAME=
TRUSTED_HOSTS=prontoar-servicos.com.br,www.prontoar-servicos.com.br
PUBLIC_BASE_URL=https://www.prontoar-servicos.com.br
GUNICORN_BIND=127.0.0.1:8000
RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
SQLITE_BUSY_TIMEOUT_MS=30000
```

### Rate limit compartilhado (obrigatorio em producao com varios workers)

O backend `memory://` guarda contadores por processo e nao e apropriado para o Gunicorn com dois workers.
Instale Redis somente na VPS do Pronto-Ar e mantenha a escuta restrita ao loopback (`127.0.0.1`).
Nao exponha a porta 6379 na internet. Antes de reiniciar a aplicacao:

```bash
sudo apt install redis-server
sudo systemctl enable --now redis-server
redis-cli ping
ss -lnt '( sport = :6379 )'
.venv/bin/pip install -r requirements.txt
```

Confirme `RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0` no ambiente do servico,
confira a origem publica HTTPS e valide a contagem entre workers apos o deploy.
Evite habilitar fallback `memory://` silencioso em producao. Configure os
headers de proxy apenas para a quantidade real de proxies confiaveis.

## 7. Garantir pastas persistentes

```bash
mkdir -p instance uploads uploads/work_orders static/img/qrcodes
```

## 8. Rodar migrations

```bash
source .venv/bin/activate
flask db upgrade
```

Se precisar popular ambiente de teste:

```bash
python seed.py
```

## 9. Testar Gunicorn manualmente

```bash
source .venv/bin/activate
gunicorn -c gunicorn.conf.py wsgi:app
```

Se subir corretamente, a aplicacao deve ouvir em `0.0.0.0:8000`.

## 10. Configurar systemd

Copie o arquivo de servico:

```bash
sudo cp deploy/systemd/pro-ar.service /etc/systemd/system/pro-ar.service
```

Edite se necessario:

```bash
sudo nano /etc/systemd/system/pro-ar.service
```

Pontos que devem conferir:

- `WorkingDirectory=/var/www/pro-ar_refrigeracao`
- `EnvironmentFile=/var/www/pro-ar_refrigeracao/.env`
- `ExecStart=/var/www/pro-ar_refrigeracao/.venv/bin/gunicorn -c /var/www/pro-ar_refrigeracao/gunicorn.conf.py wsgi:app`

Ative o servico:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pro-ar
sudo systemctl start pro-ar
sudo systemctl status pro-ar
```

Logs:

```bash
sudo journalctl -u pro-ar -f
```

## 11. Configurar Nginx

Copie a configuracao:

```bash
sudo cp deploy/nginx/pro-ar.conf /etc/nginx/sites-available/pro-ar
```

Edite dominio e caminhos:

```bash
sudo nano /etc/nginx/sites-available/pro-ar
```

Ative o site:

```bash
sudo ln -s /etc/nginx/sites-available/pro-ar /etc/nginx/sites-enabled/pro-ar
sudo nginx -t
sudo systemctl reload nginx
```

## 12. Habilitar HTTPS

Se usar Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d seudominio.com -d www.seudominio.com
```

Depois do HTTPS ativo, mantenha no `.env`:

```env
PREFERRED_URL_SCHEME=https
JWT_COOKIE_SECURE=true
SESSION_COOKIE_SECURE=true
PROXY_FIX_ENABLED=true
```

## 13. Backups minimos recomendados

- backup diario da pasta `instance/`
- backup diario da pasta `uploads/`
- backup do `.env`

Observacao:

- as fotos das ordens de servico agora ficam fora de `/static` e sao servidas por rota autenticada da aplicacao

Se continuar com SQLite em producao inicial, o arquivo critico e:

- `/var/www/pro-ar_refrigeracao/instance/pronto_ar.db`

## 14. O que este projeto ja tem pronto para VPS

- ponto de entrada WSGI em `wsgi.py`
- Gunicorn em `requirements.txt`
- configuracao base do Gunicorn em `gunicorn.conf.py`
- suporte a `ProxyFix` por variavel de ambiente
- cookies seguros configuraveis por `.env`
- SQLite com `WAL` e `busy_timeout`

## 15. Limites do setup com SQLite

Esse setup atende testes e operacao pequena, mas SQLite continua limitado para muita escrita simultanea. Quando a operacao crescer, o proximo passo natural e trocar `DATABASE_URL` para MySQL ou PostgreSQL.

## 16. Licenciamento desacoplado

Se voce pretende subir tambem a `license_api` na mesma VPS, consulte o guia dedicado:

- `deploy/HOSTINGER_LICENCIAMENTO.md`

Esse guia cobre:

- separacao entre app principal e servico de licencas;
- subdominios recomendados;
- `systemd` e `nginx` para os dois servicos;
- boas praticas para reaproveitar a `license_api` em outras aplicacoes.