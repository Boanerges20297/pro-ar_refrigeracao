# Atualização da Aplicação

Este guia descreve o procedimento recomendado para levar uma nova versão do código do ambiente de desenvolvimento para a VPS de produção do Pronto Ar.

## Objetivo

Manter o código em desenvolvimento e em produção alinhados, com o menor risco possível de indisponibilidade ou perda de dados.

Depois que a VPS já estiver preparada com o repositório Git, a rotina de atualização passa a ser basicamente `git pull` + restart do serviço. Nesse fluxo não há migração, seed ou alteração de banco.

## Fluxo Curto Via Git

Quando a VPS já estiver com o repositório Git preparado, o caminho mais rápido é atualizar só o código e manter os dados persistentes fora do checkout.

```bash
cd /var/www/pro-ar_refrigeracao
systemctl stop pro-ar
git pull --ff-only origin main
systemctl start pro-ar
systemctl status pro-ar --no-pager
```

Regras desse fluxo:

- não executar `flask db upgrade` nesse procedimento;
- não rodar `seed.py`;
- não mexer em `instance/`, `uploads/`, `keys/` ou `.env`;
- se houver foto nova ou QR Code novo, eles continuam nas pastas persistentes fora do código.

## Pré-requisitos

- acesso SSH à VPS como `root` ou usuário com permissão administrativa;
- diretório da aplicação em `/var/www/pro-ar_refrigeracao`;
- serviço systemd `pro-ar.service`;
- banco PostgreSQL configurado no arquivo `.env` da produção;
- backup recente antes de mudanças de schema.

## Fluxo recomendado

### 1. Conferir o que mudou no desenvolvimento

Antes de subir a atualização, revise os arquivos alterados no seu ambiente local:

```bash
git status --short
git diff -- app/routes/auth.py
```

Se a VPS também tiver repositório Git inicializado, você pode comparar o estado com:

```bash
git status --short
git diff --stat
```

### 2. Fazer backup do banco

Na VPS, gere um dump antes de qualquer migração:

```bash
cd /var/www/pro-ar_refrigeracao
pg_dump "$DATABASE_URL" > /root/pro-ar-backup-$(date +%F-%H%M%S).sql
```

Se preferir usar o usuário e banco explicitamente:

```bash
pg_dump -h 127.0.0.1 -U pro_ar_user -d pro_ar_refrigeracao > /root/pro-ar-backup-$(date +%F-%H%M%S).sql
```

### 3. Parar o Gunicorn

Interrompa o serviço antes de substituir arquivos ou executar migrações:

```bash
systemctl stop pro-ar
systemctl is-active pro-ar
```

O retorno esperado depois da parada é algo como `inactive`.

### 4. Atualizar os arquivos

Se a VPS estiver com Git, aplique a atualização pelo fluxo normal:

```bash
cd /var/www/pro-ar_refrigeracao
git pull
```

Se a VPS não estiver usando Git, envie apenas os arquivos alterados e substitua-os no diretório da aplicação.

Arquivos que normalmente precisam ir junto quando há mudanças de autenticação, licenciamento ou migration:

- `app/__init__.py`
- `app/models/*.py`
- `app/routes/*.py`
- `app/templates/**/*.html`
- `app/utils/*.py`
- `seed.py`
- `migrations/versions/*.py`

### 5. Instalar dependências se necessário

Se o `requirements.txt` mudou:

```bash
cd /var/www/pro-ar_refrigeracao
./.venv/bin/pip install -r requirements.txt
```

### 6. Rodar migrações

Depois da atualização do código, aplique a evolução do schema:

```bash
cd /var/www/pro-ar_refrigeracao
./.venv/bin/python -m flask --app wsgi db upgrade
```

Se o Alembic informar múltiplas heads, liste o histórico e aplique a revisão correta:

```bash
./.venv/bin/flask --app wsgi db heads
./.venv/bin/flask --app wsgi db history
```

### 7. Ajustar dados iniciais quando necessário

Se a atualização exigir reconfiguração de usuário, licença ou seed, faça isso com o serviço parado e valide diretamente no banco ou por script controlado.

Exemplo de uso para primeiro acesso do admin:

- definir senha temporária;
- marcar `must_change_password = true`;
- liberar o acesso apenas após a troca.

### 8. Subir o Gunicorn novamente

Quando tudo estiver pronto:

```bash
systemctl start pro-ar
systemctl status pro-ar --no-pager
```

### 9. Validar em produção

Após o restart, confirme que a aplicação está respondendo:

```bash
curl -I https://www.prontoar-servicos.com.br/
```

Verifique também o login e uma rota administrativa no navegador.

## Atualização de rotina com Git na VPS

Se a VPS estiver com o repositório Git inicializado, o processo mais simples é:

```bash
cd /var/www/pro-ar_refrigeracao
systemctl stop pro-ar
git pull
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m flask --app wsgi db upgrade
systemctl start pro-ar
systemctl status pro-ar --no-pager
```

## Checklist rápido

- backup feito;
- `pro-ar` parado antes das alterações;
- arquivos atualizados;
- dependências reinstaladas se necessário;
- migrações aplicadas;
- serviço voltou a `active`;
- login testado;
- página principal testada.

## Observação sobre Gunicorn

O Gunicorn deve ser encerrado pelo `systemctl stop pro-ar`, nunca finalizando processos manualmente sem necessidade. Isso evita corrupção de sessão, interrupção abrupta de requests e inconsistência durante migrações.

## Observação sobre o banco

Mudanças que adicionam colunas, tabelas ou restrições devem sempre vir acompanhadas de migração. Não altere o schema diretamente em produção sem registrar a versão correspondente no Alembic.

## Painel PostgreSQL

O pgAdmin 4 foi instalado na VPS como painel web de administração do PostgreSQL.

### Acesso

- URL: `https://www.prontoar-servicos.com.br/pgadmin4/`
- login: usuário interno criado no setup do pgAdmin

### Observações

- o acesso público é feito pelo Nginx com HTTPS;
- o Apache do pgAdmin fica apenas em loopback na VPS;
- se você mudar a porta ou o usuário inicial, atualize este guia junto.