# Arquitetura de Licenciamento Desacoplada na Hostinger

Este guia descreve como estruturar o licenciamento administrado pela BTA Solucoes em Desenvolvimento de Software para que a logica de emissao e validacao possa ser reutilizada por outras aplicacoes, com deploy viavel no plano VPS de entrada da Hostinger.

## Resposta Curta

Se a meta e suportar outras aplicacoes no futuro, a logica de licenciamento deve ficar desacoplada do produto principal em quatro niveis:

1. servico separado;
2. banco separado;
3. chaves criptograficas separadas;
4. dominio ou subdominio separado.

No inicio, isso pode ficar na mesma VPS da aplicacao principal, mas nao no mesmo processo, nao no mesmo banco e nao no mesmo contexto operacional.

## O que Significa "Extremamente Desacoplada"

Para o licenciamento ser reaproveitavel por outros sistemas, ele nao deve conhecer regras exclusivas de um cliente especifico, como nomes de telas, rotas internas ou entidades especificas do produto.

O servico de licenciamento deve conhecer apenas:

- empresa licenciada;
- identificador da instalacao;
- tipo de licenca;
- vigencia;
- limites contratados;
- lista de features;
- metadados do produto e do plano;
- estado da licenca.

Exemplo de metadados reutilizaveis:

- `product_code`: identifica qual aplicacao consumira a licenca;
- `plan_code`: identifica o plano comercial;
- `support_until`: data final do suporte contratado;
- `customer_code`: identificador interno do cliente;
- `deployment_mode`: `self_hosted` ou `managed`.

## Mesma Arquitetura ou Outra Compartimentacao?

### Recomendacao objetiva

Use a mesma VPS apenas na fase inicial, mas com compartimentacao real.

Nao recomendo rodar tudo "junto" como se fosse um unico sistema. O correto e:

- app principal em um servico;
- `license_api` em outro servico;
- `.env` separados;
- bancos separados;
- logs separados;
- portas separadas;
- reverse proxy separado;
- chaves privadas acessiveis apenas ao servico de licencas.

### Compartimentacao minima recomendada

Mesmo na mesma VPS, separe assim:

- aplicacao principal: `/var/www/pro-ar_refrigeracao/app_main`
- servico de licencas: `/var/www/pro-ar_refrigeracao/license_service`
- banco da aplicacao principal: `instance/pronto_ar.db` ou PostgreSQL dedicado
- banco da `license_api`: `license_api/data/license_api.db` ou PostgreSQL dedicado
- chave privada da `license_api`: somente no ambiente do servico de licencas
- chave publica: distribuida para a aplicacao principal

## Hostinger: qual plano comporta isso?

### Hospedagem compartilhada

Nao e recomendada para este desenho. Em hospedagem compartilhada, voce normalmente nao tem:

- `systemd`;
- `nginx` gerenciado por voce;
- processos Python persistentes sob seu controle;
- proxy reverso completo;
- liberdade para subir Gunicorn e Uvicorn do jeito correto.

Se o "plano mais popular" que voce tem em mente for hospedagem compartilhada tradicional, a resposta tecnica e: nao serve para esta arquitetura.

Se ainda assim voce quiser simular um caminho de menor custo, consulte:

- `deploy/HOSPEDAGEM_COMPARTILHADA_LICENCIAMENTO.md`

Esse guia documenta o desenho reduzido em que apenas o app principal fica na hospedagem compartilhada e a emissao de licencas permanece fora do ambiente do cliente.

### VPS Hostinger

Se for o plano VPS mais popular ou de entrada, entao sim, e viavel.

Para um inicio enxuto, esse desenho funciona bem:

- Ubuntu 22.04 ou 24.04;
- 1 VPS;
- 1 Nginx;
- 1 Gunicorn para o app principal;
- 1 Uvicorn para a `license_api`;
- 2 subdominios.

## Arquitetura Recomendada na VPS

### Dominios

Use subdominios diferentes:

- `app.seudominio.com` para o sistema principal;
- `licenses.seudominio.com` para a `license_api`.

Isso facilita:

- isolamento de cookies;
- logs;
- rate limiting;
- WAF;
- certificados SSL;
- troca futura de infraestrutura.

### Processos

Suba dois servicos distintos:

- `pro-ar.service` para o Flask/Gunicorn;
- `bta-license-service.service` para o FastAPI/Uvicorn.

### Portas internas

- app principal: `127.0.0.1:8000`
- `license_api`: `127.0.0.1:8010`

### Proxy reverso

O Nginx deve encaminhar:

- `app.seudominio.com` -> `127.0.0.1:8000`
- `licenses.seudominio.com` -> `127.0.0.1:8010`

## Modelo de Evolucao Recomendado

### Fase 1: mesma VPS, servicos separados

Esta e a melhor relacao custo/beneficio para iniciar.

Vantagens:

- custo baixo;
- deploy simples;
- reaproveita a mesma VPS;
- ainda preserva isolamento suficiente.

Desvantagens:

- se a VPS cair, caem aplicacao e licenciamento;
- ainda nao ha separacao forte de blast radius em nivel de infraestrutura.

### Fase 2: repositorio separado

Quando a `license_api` passar a atender outros sistemas alem do primeiro cliente, o ideal e mover para repositorio proprio.

Vantagens:

- ciclo de deploy independente;
- versionamento independente;
- backlog independente;
- melhor governanca para multiplos produtos.

### Fase 3: infraestrutura separada

Quando houver varios clientes ou varios produtos, o melhor desenho e:

- aplicacoes de clientes em VPSs ou ambientes separados;
- servico de licencas em VPS propria;
- banco do licenciamento separado;
- observabilidade e backups separados.

## Fluxo Tecnico Ideal

### Emissao

1. o cliente instala o sistema principal;
2. o sistema principal gera ou exibe o `ID da instalacao`;
3. sua equipe usa a `license_api` para emitir uma licenca;
4. a `license_api` assina a licenca com a chave privada;
5. o cliente recebe a chave e ativa no sistema principal.

### Validacao

1. o sistema principal recebe a chave;
2. valida localmente com a chave publica;
3. verifica empresa, vigencia, features e limites;
4. libera ou bloqueia o que estiver contratado.

### Reuso para outros produtos

Para suportar outros sistemas, o payload deve incluir ao menos:

- `product_code`;
- `plan_code`;
- `features`;
- `license_type`;
- `instance_fingerprint`;
- `company_name`;
- `issued_at`;
- `expires_at` quando aplicavel.

## Passo a Passo de Implementacao na Hostinger VPS

### 1. Criar a VPS

Na Hostinger, escolha uma VPS Linux com Ubuntu 22.04 ou 24.04.

Requisitos minimos práticos para iniciar:

- 1 vCPU;
- 2 GB RAM;
- SSD;
- acesso root ou usuario com sudo.

### 2. Apontar DNS

Crie estes registros:

- `A` para `app.seudominio.com` apontando para o IP da VPS;
- `A` para `licenses.seudominio.com` apontando para o mesmo IP.

### 3. Instalar pacotes do sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git certbot python3-certbot-nginx
```

### 4. Criar estrutura de diretorios

```bash
sudo mkdir -p /var/www/pro-ar_refrigeracao/app_main
sudo mkdir -p /var/www/pro-ar_refrigeracao/license_service
sudo chown -R $USER:$USER /var/www/pro-ar_refrigeracao
```

### 5. Publicar o codigo

Se voce ainda mantiver tudo no mesmo repositorio, pode clonar uma vez e usar duas areas de trabalho logicas. Exemplo:

```bash
cd /var/www/pro-ar_refrigeracao/app_main
git clone <SEU_REPOSITORIO> .

cd /var/www/pro-ar_refrigeracao/license_service
git clone <SEU_REPOSITORIO> .
```

Se quiser economizar espaco, e possivel usar um unico checkout, mas para compartimentacao mais limpa eu recomendo dois caminhos distintos desde ja.

### 6. Criar ambientes virtuais separados

#### App principal

```bash
cd /var/www/pro-ar_refrigeracao/app_main
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### License API

```bash
cd /var/www/pro-ar_refrigeracao/license_service
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r license_api/requirements.txt
```

### 7. Configurar ambiente do app principal

```bash
cd /var/www/pro-ar_refrigeracao/app_main
cp .env.example .env
nano .env
```

Valores base sugeridos:

```env
SECRET_KEY=gere-um-valor-forte
JWT_SECRET_KEY=gere-outro-valor-forte
DATABASE_URL=sqlite:////var/www/pro-ar_refrigeracao/app_main/instance/pronto_ar.db
UPLOAD_ROOT=/var/www/pro-ar_refrigeracao/app_main/uploads
PREFERRED_URL_SCHEME=https
JWT_COOKIE_SECURE=true
SESSION_COOKIE_SECURE=true
PROXY_FIX_ENABLED=true
PROXY_FIX_X_FOR=1
PROXY_FIX_X_PROTO=1
PROXY_FIX_X_HOST=1
PROXY_FIX_X_PORT=1
TRUSTED_HOSTS=app.seudominio.com
LICENSE_PUBLIC_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_public.pem
LICENSE_INSTALLATION_ID_PATH=/var/www/pro-ar_refrigeracao/app_main/instance/installation_id.txt
LICENSE_ALLOW_LEGACY_TOKENS=false
```

### 8. Configurar ambiente da license_api

```bash
cd /var/www/pro-ar_refrigeracao/license_service
cp license_api/.env.example license_api/.env
nano license_api/.env
```

Valores base sugeridos para o modo inicial com SQLite local na mesma VPS:

```env
LICENSE_API_TOKEN=gere-um-token-forte
LICENSE_API_DATABASE_URL=sqlite:////var/www/pro-ar_refrigeracao/license_service/license_api/data/license_api.db
LICENSE_PRIVATE_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_private.pem
LICENSE_PUBLIC_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_public.pem
LICENSE_ALLOW_PERPETUAL=true
```

Se quiser simplificar ainda mais, pode omitir `LICENSE_API_DATABASE_URL`, porque a `license_api` ja assume SQLite local por padrao quando a variavel nao esta definida.

### 9. Criar diretorios persistentes

```bash
mkdir -p /var/www/pro-ar_refrigeracao/app_main/instance
mkdir -p /var/www/pro-ar_refrigeracao/app_main/uploads/work_orders
mkdir -p /var/www/pro-ar_refrigeracao/app_main/static/img/qrcodes
mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/data
mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/keys
```

Esses diretórios guardam o banco SQLite, as chaves Ed25519 e os arquivos persistentes da aplicacao principal.

### 10. Aplicar migrations do app principal

```bash
cd /var/www/pro-ar_refrigeracao/app_main
source .venv/bin/activate
flask db upgrade
```

### 11. Gerar chaves da license_api

As chaves tambem podem ser geradas automaticamente no startup, mas o ideal e validar isso antes:

```bash
cd /var/www/pro-ar_refrigeracao/license_service
source .venv/bin/activate
python license_api/scripts/generate_keys.py
```

Se voce ja tiver uma chave privada antiga e quiser manter compatibilidade, copie os arquivos PEM para a pasta `license_api/keys/` antes de iniciar o servico.

### 12. Testar servicos manualmente

#### App principal

```bash
cd /var/www/pro-ar_refrigeracao/app_main
source .venv/bin/activate
gunicorn -c gunicorn.conf.py wsgi:app
```

#### License API

```bash
cd /var/www/pro-ar_refrigeracao/license_service
source .venv/bin/activate
uvicorn license_api.main:app --host 127.0.0.1 --port 8010
```

### 13. Instalar servicos systemd

Copie os templates deste repositorio:

```bash
sudo cp /var/www/pro-ar_refrigeracao/app_main/deploy/systemd/pro-ar.service /etc/systemd/system/pro-ar.service
sudo cp /var/www/pro-ar_refrigeracao/app_main/deploy/systemd/bta-license-service.service /etc/systemd/system/bta-license-service.service
```

Revise os caminhos e ative:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pro-ar
sudo systemctl enable bta-license-service
sudo systemctl start pro-ar
sudo systemctl start bta-license-service
sudo systemctl status pro-ar
sudo systemctl status bta-license-service
```

### 14. Instalar configuracoes Nginx

Use os exemplos deste repositorio:

```bash
sudo cp /var/www/pro-ar_refrigeracao/app_main/deploy/nginx/pro-ar.conf /etc/nginx/sites-available/pro-ar
sudo cp /var/www/pro-ar_refrigeracao/app_main/deploy/nginx/license-api.conf /etc/nginx/sites-available/pro-ar-license
```

Ative os dois sites:

```bash
sudo ln -s /etc/nginx/sites-available/pro-ar /etc/nginx/sites-enabled/pro-ar
sudo ln -s /etc/nginx/sites-available/pro-ar-license /etc/nginx/sites-enabled/pro-ar-license
sudo nginx -t
sudo systemctl reload nginx
```

### 15. Habilitar HTTPS

```bash
sudo certbot --nginx -d app.seudominio.com -d licenses.seudominio.com
```

### 16. Validar funcionamento

#### Sistema principal

- abrir `https://app.seudominio.com`
- fazer login administrativo
- verificar a tela de licenca em `/admin/settings`

#### License API

- abrir `https://licenses.seudominio.com/admin/login`
- entrar com o token administrativo
- emitir uma licenca de teste
- ativar essa chave no sistema principal

Nesse desenho, o cliente consulta o subdominio de licenciamento pela internet, mas o armazenamento continua local na VPS, em SQLite.

## Politica de Seguranca Recomendada

### Nunca distribuir a chave privada

A chave privada deve existir somente no servico de licenciamento.

### Public key compartilhada, private key isolada

- a chave publica pode ser lida pelo app principal;
- a chave privada nao deve ficar no ambiente da aplicacao principal.

### Restricoes recomendadas

- firewall permitindo apenas `80` e `443` externamente;
- portas `8000` e `8010` apenas internas;
- permissao restrita nos arquivos `license_api/keys`;
- token administrativo forte e rotacionavel;
- HTTPS obrigatorio.

## Como Tornar a License API Reutilizavel por Outros Produtos

Para sair do modo "licenciamento de um cliente especifico" e virar "servico de licenciamento da sua empresa", a evolucao recomendada e:

1. adicionar `product_code` ao payload;
2. adicionar `plan_code` ao payload;
3. padronizar a lista de `features` por produto;
4. separar a documentacao de produto da documentacao do servico de licencas;
5. mover a `license_api` para repositorio proprio quando for atender o segundo produto real.

## Decisao Recomendada

Se voce vai usar o plano VPS de entrada ou o plano VPS mais popular da Hostinger, a melhor decisao hoje e:

- manter o app principal e a `license_api` na mesma VPS;
- separar em dois servicos, duas configuracoes e dois subdominios;
- usar a `license_api` como backoffice interno;
- manter a validacao da licenca local em cada aplicacao cliente;
- planejar repositorio e infraestrutura separados quando o segundo produto entrar em producao.

## Comandos Exatos para Subir a license_api na Mesma VPS

Use esta sequencia se voce quiser fazer o deploy agora, sem adaptar o guia.

### 1. Preparar a pasta

```bash
sudo mkdir -p /var/www/pro-ar_refrigeracao/license_service
sudo chown -R $USER:$USER /var/www/pro-ar_refrigeracao/license_service
cd /var/www/pro-ar_refrigeracao/license_service
```

### 2. Clonar o repositorio

```bash
git clone https://github.com/Boanerges20297/license_api.git .
```

### 3. Criar o ambiente virtual e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Criar o arquivo de ambiente

```bash
cp .env.example .env
nano .env
```

Conteudo minimo recomendado:

```env
LICENSE_API_TOKEN=troque-por-um-token-forte
LICENSE_API_DATABASE_URL=sqlite:////var/www/pro-ar_refrigeracao/license_service/license_api/data/license_api.db
LICENSE_PRIVATE_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_private.pem
LICENSE_PUBLIC_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_public.pem
LICENSE_ALLOW_PERPETUAL=true
LICENSE_API_AUTO_CREATE_SCHEMA=true
```

### 5. Criar diretorios persistentes

```bash
mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/data
mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/keys
```

### 6. Gerar as chaves

```bash
source .venv/bin/activate
python license_api/scripts/generate_keys.py
```

### 7. Subir manualmente para teste

```bash
source .venv/bin/activate
uvicorn license_api.main:app --host 127.0.0.1 --port 8010
```

### 8. Instalar o service systemd

```bash
sudo cp deploy/systemd/bta-license-service.service /etc/systemd/system/bta-license-service.service
sudo systemctl daemon-reload
sudo systemctl enable bta-license-service
sudo systemctl start bta-license-service
sudo systemctl status bta-license-service
```

### 9. Instalar o Nginx do subdominio

```bash
sudo cp deploy/nginx/license-api.conf /etc/nginx/sites-available/pro-ar-license
sudo ln -s /etc/nginx/sites-available/pro-ar-license /etc/nginx/sites-enabled/pro-ar-license
sudo nginx -t
sudo systemctl reload nginx
```

### 10. Emitir HTTPS

```bash
sudo certbot --nginx -d licenses.seudominio.com
```

### 11. Testar

```bash
curl -I https://licenses.seudominio.com/health
```

Se a resposta vier `200`, a `license_api` esta no ar.

## Sequencia Unica de Comandos da license_api

Se voce quiser executar tudo em uma vez, use esta ordem no SSH da VPS:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git certbot python3-certbot-nginx

sudo mkdir -p /var/www/pro-ar_refrigeracao/license_service
sudo chown -R $USER:$USER /var/www/pro-ar_refrigeracao/license_service
cd /var/www/pro-ar_refrigeracao/license_service

git clone https://github.com/Boanerges20297/license_api.git .

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
nano .env

mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/data
mkdir -p /var/www/pro-ar_refrigeracao/license_service/license_api/keys

source .venv/bin/activate
python license_api/scripts/generate_keys.py

source .venv/bin/activate
uvicorn license_api.main:app --host 127.0.0.1 --port 8010

sudo cp deploy/systemd/bta-license-service.service /etc/systemd/system/bta-license-service.service
sudo systemctl daemon-reload
sudo systemctl enable bta-license-service
sudo systemctl start bta-license-service
sudo systemctl status bta-license-service

sudo cp deploy/nginx/license-api.conf /etc/nginx/sites-available/pro-ar-license
sudo ln -s /etc/nginx/sites-available/pro-ar-license /etc/nginx/sites-enabled/pro-ar-license
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d licenses.seudominio.com

curl -I https://licenses.seudominio.com/health
```

Ordem do que configurar no `.env`:

```env
LICENSE_API_TOKEN=troque-por-um-token-forte
LICENSE_API_DATABASE_URL=sqlite:////var/www/pro-ar_refrigeracao/license_service/license_api/data/license_api.db
LICENSE_PRIVATE_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_private.pem
LICENSE_PUBLIC_KEY_PATH=/var/www/pro-ar_refrigeracao/license_service/license_api/keys/ed25519_public.pem
LICENSE_ALLOW_PERPETUAL=true
LICENSE_API_AUTO_CREATE_SCHEMA=true
```