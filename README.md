# Pronto Ar Refrigeração

Sistema web interno para gestão operacional de empresas de refrigeração e climatização. O projeto centraliza clientes, equipamentos, ordens de serviço, manutenção preventiva, geração e leitura de QR Code, controle por perfil de usuário, notificações operacionais e auditoria administrativa.

Desenvolvido por Boanerges Teixeira de Almeida.

## Índice

- Visão Geral
- Escopo Funcional
- Perfis e Permissões
- Arquitetura da Aplicação
- Estrutura do Projeto
- Modelos de Dados
- Fluxos Operacionais
- Sistema de Auditoria
- Notificações
- Tecnologias e Dependências
- Requisitos de Ambiente
- Instalação
- Configuração
- Banco de Dados e Migrações
- Execução
- Seed de Dados
- Acesso em Rede e Celular
- Segurança
- Operação Administrativa
- Convenções do Projeto
- Documentação Complementar
- Checklist de Produção

### Execução com Gunicorn

Para testes em ambiente Linux, VPS ou hospedagem no estilo Hostinger VPS, use Gunicorn com o ponto de entrada WSGI do projeto:

```bash
gunicorn -c gunicorn.conf.py wsgi:app
```

Se preferir informar tudo diretamente na linha de comando:

```bash
gunicorn --workers 2 --bind 0.0.0.0:8000 --timeout 120 wsgi:app
```

Observações:

- Gunicorn é voltado a Linux/macOS e deve ser executado no servidor de hospedagem.
- Em produção, o recomendado é colocar Nginx na frente do Gunicorn.
- A aplicação continua usando `.env` via `python-dotenv` no ponto de entrada `wsgi.py`.

## Visão Geral

O Pronto Ar foi construído para controlar o ciclo completo de atendimento técnico:

- cadastro de clientes;
- cadastro de equipamentos por cliente;
- geração e leitura de QR Code para acesso rápido ao equipamento;
- criação, edição, acompanhamento e conclusão de ordens de serviço;
- agendamento de manutenção preventiva;
- separação de acesso por perfil;
- rastreamento de ações via log de auditoria.

Além da operação técnica, a aplicação também contempla uma camada administrativa com painel, relatórios, configuração visual da empresa e monitoramento de atividades recentes.

## Escopo Funcional

### Funcionalidades principais

| Módulo | Descrição |
|---|---|
| Autenticação | Login com JWT em cookie HttpOnly e proteção CSRF por Flask-WTF |
| Clientes | Cadastro, edição, listagem e consulta de equipamentos por cliente |
| Equipamentos | Cadastro, edição, visualização detalhada, QR Code e histórico associado |
| Ordens de Serviço | Criação, edição, histórico, agrupamento por cliente, exportação PDF e acompanhamento por status |
| Manutenção | Agendamento preventivo, listagem, fechamento de manutenção e alertas por vencimento |
| Funcionários | Gestão de usuários com níveis admin, secretary e user |
| Dashboard Admin | Métricas, visão geral financeira, alertas operacionais e acesso à auditoria |
| Dashboard Secretary | Operação administrativa restrita para agendamento e acompanhamento |
| Dashboard Técnico | Visão das ordens atribuídas e alertas do próprio técnico |
| Auditoria | Registro de ações com retenção automática de 7 dias |
| Notificações | Alertas por perfil para serviços do dia, atrasos e manutenções |
| Tema da Empresa | Nome, logo e cores configuráveis no painel administrativo |

## Perfis e Permissões

O sistema separa função operacional de nível de acesso. O campo principal de autorização é `permission_level`.

| Permissão | Objetivo | Acessos principais |
|---|---|---|
| `admin` | Gestão completa | dashboard administrativo, relatórios, financeiro, funcionários, configurações, auditoria |
| `secretary` | Operação administrativa restrita | dashboard, clientes, equipamentos, agendamentos, manutenção, conclusão de OS |
| `user` | Técnico de campo | dashboard técnico, serviços atribuídos, acesso operacional limitado aos próprios dados |

### Restrições do perfil secretary

O perfil `secretary` foi desenhado para atuação administrativa sem exposição de dados sensíveis. Em regra, ele:

- pode agendar ordens de serviço;
- pode editar agendamentos;
- pode concluir ordens pendentes ou em andamento;
- pode consultar clientes, equipamentos e manutenção;
- não deve acessar dados financeiros;
- não deve manipular fotos antes/depois do serviço;
- não deve excluir registros;
- não pode acessar os logs de auditoria.

## Arquitetura da Aplicação

### Backend

- Flask com padrão application factory em `app/__init__.py`.
- Blueprints separados por domínio e perfil.
- SQLAlchemy para mapeamento ORM.
- Flask-Migrate/Alembic para migrações.
- Flask-JWT-Extended para autenticação baseada em cookies.
- Flask-WTF para proteção CSRF em formulários.

### Frontend

- Jinja2 para renderização server-side.
- Tailwind CSS via CDN para layout e componentes.
- Font Awesome para ícones.
- HTML5 QRCode para leitura por câmera.
- Componentes modais e dropdowns implementados no próprio template base.

### Organização por responsabilidade

- `app/routes`: regras de entrada HTTP e fluxos da aplicação.
- `app/models`: estrutura persistida no banco.
- `app/templates`: interface por módulo.
- `app/utils`: autenticação auxiliar, auditoria, notificações, imagem e decorators.
- `migrations`: histórico de schema.

## Estrutura do Projeto

```text
pro-ar_refrigeracao/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── audit_log.py
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── equipment.py
│   │   ├── license.py
│   │   ├── maintenance.py
│   │   ├── service.py
│   │   ├── user.py
│   │   └── workorder.py
│   ├── routes/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── clients.py
│   │   ├── equipment.py
│   │   ├── main.py
│   │   ├── maintenance.py
│   │   ├── reports.py
│   │   ├── secretary.py
│   │   ├── services.py
│   │   └── technician.py
│   ├── templates/
│   │   ├── admin/
│   │   ├── auth/
│   │   ├── clients/
│   │   ├── email/
│   │   ├── equipment/
│   │   ├── maintenance/
│   │   ├── reports/
│   │   ├── secretary/
│   │   ├── services/
│   │   ├── technician/
│   │   └── base.html
│   └── utils/
│       ├── audit.py
│       ├── audit_cli.py
│       ├── decorators.py
│       ├── email.py
│       ├── images.py
│       ├── license.py
│       └── notifications.py
├── deploy/
│   ├── HOSTINGER_VPS.md
│   ├── HOSTINGER_LICENCIAMENTO.md
│   ├── HOSPEDAGEM_COMPARTILHADA_LICENCIAMENTO.md
│   ├── nginx/
│   └── systemd/
├── docs/
│   └── LICENCIAMENTO_COMERCIAL.md
├── instance/
├── license_api/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   ├── service.py
│   ├── templates/
│   ├── scripts/
│   └── README.md
├── migrations/
│   └── versions/
├── static/
│   └── img/
│       └── qrcodes/
├── requirements.txt
├── run.py
├── seed.py
└── README.md
```

## Modelos de Dados

### User

Representa administradores, secretários e técnicos.

Campos relevantes:

- `name`
- `email`
- `password_hash`
- `permission_level`
- `job_title`
- `role` legado para compatibilidade
- `specialty`
- `is_active`

### Client

Entidade de cliente/empresa atendida.

Campos usuais:

- nome;
- email;
- telefone;
- endereço.

### Equipment

Equipamento associado a um cliente.

Campos relevantes:

- `name`
- `brand`
- `model`
- `serial_number`
- `location`
- `qr_code_path`
- `maintenance_interval`
- `client_id`

Relacionamentos:

- histórico de ordens de serviço;
- agendamentos de manutenção.

### ServiceCatalog

Catálogo base de tipos de serviço com descrição, valor base e duração estimada.

### WorkOrder

Ordem de serviço operacional do sistema.

Campos relevantes:

- `status` (`Pending`, `In Progress`, `Completed`, `Cancelled`)
- `scheduled_date`
- `completed_date`
- `description`
- `photo_before`
- `photo_after`
- `total_value`
- `paid_value`
- `is_paid`
- `client_id`
- `equipment_id`
- `service_id`
- `technician_id`
- `created_at`

### MaintenanceSchedule

Agenda de manutenção preventiva por equipamento.

Campos relevantes:

- `equipment_id`
- `next_maintenance_date`
- `last_maintenance_date`
- `description`
- `is_active`

### AuditLog

Registro de auditoria de ações do sistema.

Campos relevantes:

- `user_id`
- `action`
- `resource_type`
- `resource_id`
- `resource_name`
- `status`
- `ip_address`
- `user_agent`
- `details`
- `timestamp`

### AppConfig

Configuração persistida da aplicação.

Campos relevantes:

- `company_name`
- `logo_path`
- `primary_color`
- `secondary_color`
- `background_color`
- `text_color`
- `navbar_bg_color`
- `navbar_link_color`
- `navbar_hover_color`
- `smtp_provider`
- `smtp_server`
- `smtp_port`
- `smtp_user`
- `smtp_password`
- `smtp_use_tls`
- `smtp_use_ssl`
- `mail_sender_name`

### License

Estado local da licença instalada nesta instância.

Campos relevantes:

- `license_key`
- `status`
- `company_name`
- `instance_fingerprint`
- `issued_at`
- `activated_at`
- `expires_at`
- `last_validated_at`
- `last_validation_status`
- `last_validation_error`
- `max_users`
- `max_admin_users`
- `max_secretary_users`
- `feature_flags`
- `warning_days`
- `grace_days`

## Fluxos Operacionais

### 1. Atendimento técnico padrão

1. cadastrar cliente;
2. cadastrar equipamento;
3. criar ordem de serviço;
4. atribuir técnico;
5. agendar data e hora;
6. acompanhar status;
7. concluir atendimento;
8. consultar histórico do equipamento.

### 2. Fluxo do secretariado

1. acessar o dashboard do perfil `secretary`;
2. criar agendamento de ordem de serviço;
3. editar técnico, data e descrição quando necessário;
4. consultar pendências na lista dedicada;
5. concluir a OS pela própria lista de pendentes;
6. permanecer no fluxo operacional sem ser redirecionado ao dashboard ao concluir.

### 3. Fluxo de manutenção preventiva

1. cadastrar equipamento com intervalo de manutenção;
2. criar agendamento de manutenção;
3. acompanhar vencimento e próximos 7 dias;
4. marcar manutenção como concluída;
5. gerar novo ciclo preventivo conforme rotina operacional.

### 4. Fluxo de equipamento com QR Code

1. cadastrar equipamento;
2. gerar QR Code;
3. imprimir ou baixar o código;
4. ler o código via câmera;
5. abrir diretamente a página do equipamento.

### 5. Fluxo de recuperação de senha

1. acessar a tela de login;
2. acionar `Esqueci minha senha`;
3. informar o e-mail cadastrado;
4. receber link temporário de redefinição por e-mail quando o SMTP estiver configurado;
5. abrir o link de redefinição;
6. informar nova senha obedecendo a política de complexidade;
7. concluir a troca e voltar ao login.

### 6. Fluxo de ativação e revalidação de licença

1. acessar `/admin/settings` com perfil administrativo;
2. copiar o `ID da instalação` exibido pelo sistema;
3. solicitar ou gerar uma licença compatível com `company_name` e `instance_fingerprint`;
4. colar a chave no formulário de ativação;
5. validar status, vigência, features e limites contratados;
6. usar o botão de revalidação quando for necessário conferir novamente a chave salva.

### 7. Fluxo de fotos de ordem de serviço

1. anexar foto antes/depois ao criar ou editar uma OS;
2. armazenar o arquivo em `UPLOAD_ROOT` fora de `/static`;
3. servir o arquivo por rota autenticada;
4. permitir acesso apenas a perfis autorizados ou ao técnico vinculado à OS.

## Sistema de Auditoria

O sistema possui trilha de auditoria administrativa com retenção curta para operação interna.

### O que é registrado

- login com sucesso e falha;
- logout;
- reset de senha;
- criação e atualização de entidades instrumentadas;
- contexto de IP e user-agent;
- detalhes complementares serializados em JSON.

### Regras de retenção

- retenção padrão de 7 dias;
- limpeza automática disponível via utilitário do modelo `AuditLog.cleanup_old_logs(days=7)`;
- comandos CLI específicos para limpeza e estatística.

### Comandos CLI de auditoria

```bash
flask audit-cleanup
flask audit-cleanup --days 7
flask audit-stats
flask audit-cleanup-schedule --interval 1
```

### Acesso administrativo

Rotas de auditoria:

- `GET /admin/audit-logs`
- `GET /admin/audit-logs/stats`
- `GET /admin/audit-logs/export`

Essas rotas devem ser acessadas apenas por `admin`.

## Notificações

As notificações são carregadas no contexto global via `app.utils.notifications.get_alerts`.

### Admin

- serviços do dia;
- serviços atrasados;
- ordens sem técnico;
- manutenções atrasadas;
- manutenções dos próximos 7 dias.

### Secretary

- serviços do dia;
- serviços atrasados;
- ordens sem técnico;
- manutenções próximas.

### Técnico

- serviços atrasados atribuídos ao próprio técnico.

## Tecnologias e Dependências

### Backend

- Flask 3.1.3
- Flask-SQLAlchemy 3.1.1
- Flask-Migrate 4.0.5
- Flask-JWT-Extended 4.7.0
- Flask-Bcrypt 1.0.1
- Flask-Limiter 3.8.0
- Flask-WTF 1.2.1
- SQLAlchemy 2.0.36
- Werkzeug 3.1.3

### Utilitários adicionais

- python-dotenv 1.0.1
- qrcode[pil] 8.2
- Pillow 12.2.0
- python-dateutil 2.9.0.post0
- reportlab 4.0.9
- cryptography 45.0.4

### Frontend

- Jinja2
- Tailwind CSS via CDN
- Font Awesome
- Google Fonts Inter
- html5-qrcode

## Requisitos de Ambiente

- Python 3.10 ou superior
- pip
- ambiente virtual recomendado
- SQLite para desenvolvimento
- PostgreSQL recomendado para produção

## Instalação

```bash
git clone <url-do-repositorio>
cd pro-ar_refrigeracao

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuração

Arquivo principal: `app/config.py`.

Variáveis de ambiente suportadas:

| Variável | Uso | Padrão |
|---|---|---|
| `SECRET_KEY` | chave do Flask e formulários | gerada aleatoriamente |
| `DATABASE_URL` | string de conexão do banco | `sqlite:///pronto_ar.db` |
| `UPLOAD_ROOT` | raiz de armazenamento de uploads | `uploads` |
| `MAX_CONTENT_LENGTH` | tamanho máximo de upload em bytes | `8388608` |
| `RATELIMIT_STORAGE_URI` | backend do rate limit | `memory://` |
| `PREFERRED_URL_SCHEME` | esquema padrão para URLs externas | `http` |
| `SERVER_NAME` | host preferencial do Flask | vazio |
| `TRUSTED_HOSTS` | lista de hosts confiáveis | vazio |
| `JWT_SECRET_KEY` | chave JWT | gerada aleatoriamente |
| `LICENSE_SIGNING_SECRET` | fallback legado para desenvolvimento/local | usa `SECRET_KEY` |
| `LICENSE_PUBLIC_KEY_PATH` | caminho da chave pública usada para validar licenças emitidas externamente | `license_api/keys/ed25519_public.pem` |
| `LICENSE_WARNING_DAYS` | antecedência para aviso de expiração | `15` |
| `LICENSE_GRACE_DAYS` | carência após expiração | `7` |
| `LICENSE_INSTANCE_ID` | identificador fixo opcional da instalação | vazio |
| `LICENSE_INSTALLATION_ID_PATH` | arquivo local que guarda o identificador estável da instalação | `instance/installation_id.txt` |
| `LICENSE_ALLOW_LEGACY_TOKENS` | permite tokens antigos em desenvolvimento/transição | `false` |
| `JWT_COOKIE_SECURE` | exige cookie JWT em HTTPS | `false` |
| `JWT_COOKIE_SAMESITE` | política SameSite do cookie JWT | `Lax` |
| `SESSION_COOKIE_SECURE` | exige cookie de sessão em HTTPS | `false` |
| `SESSION_COOKIE_HTTPONLY` | protege cookie de sessão contra JS | `true` |
| `SESSION_COOKIE_SAMESITE` | política SameSite da sessão | `Lax` |
| `PROXY_FIX_ENABLED` | habilita `ProxyFix` | `false` |
| `PROXY_FIX_X_FOR` | confiança em `X-Forwarded-For` | `1` |
| `PROXY_FIX_X_PROTO` | confiança em `X-Forwarded-Proto` | `1` |
| `PROXY_FIX_X_HOST` | confiança em `X-Forwarded-Host` | `1` |
| `PROXY_FIX_X_PORT` | confiança em `X-Forwarded-Port` | `1` |
| `PROXY_FIX_X_PREFIX` | confiança em `X-Forwarded-Prefix` | `0` |

### Observações de configuração

- `JWT_ACCESS_TOKEN_EXPIRES = 1800` define sessão de 30 minutos.
- `JWT_TOKEN_LOCATION = ['cookies']` usa cookie como transporte.
- `JWT_COOKIE_SECURE = False` no ambiente atual; em produção deve ser `True` com HTTPS.
- `JWT_COOKIE_CSRF_PROTECT = False` porque o projeto usa CSRF do Flask-WTF nos formulários.
- `TRUSTED_HOSTS` e `PROXY_FIX_*` são relevantes quando a aplicação estiver atrás de proxy reverso.
- `LICENSE_ALLOW_LEGACY_TOKENS` deve permanecer desabilitado em produção.

Exemplo em PowerShell:

```powershell
$env:SECRET_KEY = "chave-secreta-flask"
$env:JWT_SECRET_KEY = "chave-secreta-jwt"
$env:DATABASE_URL = "sqlite:///pronto_ar.db"
$env:UPLOAD_ROOT = "uploads"
$env:LICENSE_PUBLIC_KEY_PATH = "license_api/keys/ed25519_public.pem"
$env:LICENSE_ALLOW_LEGACY_TOKENS = "false"
```

## Banco de Dados e Migrações

O projeto usa Alembic via Flask-Migrate.

Comandos principais:

```bash
flask db upgrade
flask db migrate -m "descricao"
flask db downgrade
```

Migração relevante do estado atual:

- criação da tabela `audit_log`;
- criação da tabela `license` para armazenamento do estado local da licença.

Observação operacional:

- o arquivo SQLite de desenvolvimento fica em `instance/pronto_ar.db`;
- esse arquivo representa estado local de execução e não deve ser tratado como fonte de verdade de deploy.

## Execução

Subida local da aplicação:

```bash
python run.py
```

Comportamento atual:

- carrega `.env` no início;
- cria a aplicação com `create_app()`;
- sobe em `0.0.0.0:5000` com `debug=True`.

URL local padrão:

- `http://127.0.0.1:5000`
- `http://localhost:5000`

## Seed de Dados

O projeto possui `seed.py` para recriar o banco com dados de demonstração.

Comando:

```bash
python seed.py
```

O seed atual:

- derruba e recria as tabelas;
- cria configuração inicial da empresa;
- cria uma licença trial premium assinada para ambiente de demonstração;
- cria usuários base;
- cria clientes e equipamentos de exemplo;
- cria catálogo de serviços;
- gera ordens de serviço de demonstração com datas aleatórias.

Credenciais de seed informadas pelo próprio script:

- admin: `admin@prontoar.com` / `admin123`
- técnico: `carlos@prontoar.com` / `tech1234`
- técnico adicional: `joao@prontoar.com` / `tech1234`

## Acesso em Rede e Celular

Para testar em outro dispositivo na mesma rede:

1. descobrir o IPv4 da máquina;
2. liberar a porta 5000 no firewall;
3. acessar `http://SEU_IP:5000`.

Exemplo:

```powershell
ipconfig | findstr "IPv4"
netsh advfirewall firewall add rule name="Flask 5000" dir=in action=allow protocol=TCP localport=5000
```

Leitura de câmera em celular pode exigir HTTPS quando o navegador bloquear `getUserMedia` em HTTP externo.

## Segurança

Controles existentes no projeto:

- hash de senha com Bcrypt;
- JWT em cookie HttpOnly;
- CSRF por Flask-WTF em formulários;
- uso de ORM em vez de SQL manual na maior parte dos fluxos;
- autoescape do Jinja2;
- validação de uploads e redimensionamento de imagem;
- separação de acesso por decorator;
- restrição específica para secretariado em rotas sensíveis;
- trilha de auditoria administrativa.

Pontos de atenção:

- o modo debug está ativo no `run.py`;
- `JWT_COOKIE_SECURE` ainda está desligado para desenvolvimento;
- SQLite não é a melhor opção para produção concorrente;
- o acesso por perfil depende da consistência entre `permission_level` e regras das rotas.

## Operação Administrativa

### Rotas e áreas principais

| Área | Finalidade |
|---|---|
| `/admin/dashboard` | visão geral gerencial |
| `/admin/settings` | identidade visual e configurações da empresa |
| `/admin/license` | ativação ou renovação da licença |
| `/admin/license/revalidate` | revalidação da chave salva |
| `/admin/audit-logs` | consulta de auditoria |
| `/auth/forgot-password` | solicitação de recuperação de senha |
| `/auth/reset-password/<token>` | redefinição de senha por token |
| `/secretary/dashboard` | operação administrativa restrita |
| `/secretary/workorders/pending` | fila de ordens pendentes/em andamento |
| `/services` | listagem agrupada de ordens por cliente |
| `/services/history` | histórico completo com filtros |
| `/services/export-pdf` | exportação PDF do histórico filtrado |
| `/services/uploads/work-orders/<arquivo>` | entrega autenticada de fotos de OS |
| `/maintenance` | agenda preventiva |
| `/equipment/view/<serial>` | detalhe do equipamento via código/QR |
| `/equipment/regenerate-qr/<id>` | regeneração de QR Code |

### Comportamento por login

Após autenticar:

- `admin` vai para o dashboard administrativo;
- `secretary` vai para o dashboard operacional;
- `user` vai para o dashboard técnico.

## Convenções do Projeto

- Blueprints nomeados por domínio.
- Templates organizados por módulo.
- Decorators centralizados em `app/utils/decorators.py`.
- Notificações centralizadas no contexto global da aplicação.
- Auditoria desacoplada em utilitário específico.
- O README funciona como visão geral do produto; detalhes comerciais e de deploy ficam em documentos auxiliares.

## Documentação Complementar

- `docs/LICENCIAMENTO_COMERCIAL.md`: modelos comerciais, planos, precificação e regras operacionais.
- `license_api/README.md`: emissão, verificação, revogação e painel administrativo do serviço de licenças.
- `deploy/HOSTINGER_VPS.md`: deploy do app principal em VPS.
- `deploy/HOSTINGER_LICENCIAMENTO.md`: deploy desacoplado do serviço de licenças em VPS.
- `deploy/HOSPEDAGEM_COMPARTILHADA_LICENCIAMENTO.md`: cenário reduzido para hospedagem compartilhada.

## Controle de Licença

O sistema agora possui uma camada de licenciamento com chave assinada, validação local, controle de vencimento, período de carência, limites contratados por tipo de usuário e bloqueio operacional quando a licença estiver inválida ou expirada além da carência.

Comportamentos implementados:

1. ativação e renovação pela área administrativa em `/admin/settings`;
2. validação local por chave pública quando a licença é emitida externamente;
3. fallback legado por `LICENSE_SIGNING_SECRET` para desenvolvimento e transição;
4. checagem de `company_name` e `instance_fingerprint` para vincular a chave à empresa e à instalação corretas;
5. suporte a licença perpétua e por assinatura;
6. avisos globais quando a licença está prestes a vencer;
7. bloqueio operacional quando não existe licença ativa válida;
8. auditoria para ativação, revalidação, troca de chave, bloqueio de login e excesso de limites;
9. limite de usuários ativos, administradores e secretárias conforme o plano.

Observação:

- a emissão centralizada/remota agora pode ser feita pela API separada em `license_api/`, enquanto o Flask valida localmente a licença recebida.
- o detalhamento comercial completo dos modelos, planos, preços sugeridos e regras de operação está em `docs/LICENCIAMENTO_COMERCIAL.md`.

### Planos sugeridos

#### Basic

Recursos incluídos:

- autenticação e controle de sessão;
- dashboard operacional por perfil;
- cadastro de clientes;
- cadastro e consulta de equipamentos;
- QR Code por equipamento;
- ordens de serviço e histórico operacional;
- gestão de funcionários;
- limites de usuários conforme a licença.

Recursos não incluídos por padrão:

- relatórios gerenciais;
- logs de auditoria;
- manutenção preventiva;
- personalização avançada da identidade visual;
- configuração SMTP e recuperação de senha por e-mail.

#### Premium

Inclui tudo do Basic e adiciona os módulos premium abaixo:

- `reports`: relatórios financeiros, por cliente e por serviços;
- `audit`: visualização e exportação de logs de auditoria;
- `maintenance`: agenda e baixa de manutenção preventiva;
- `branding`: personalização visual avançada do sistema;
- `email`: configuração SMTP e fluxos de recuperação por e-mail.

Sugestão comercial resumida:

- `Basic` e `Premium` definem funcionalidades;
- `Perpétua` e `Assinatura` definem forma de cobrança e vigência;
- contratos de manutenção/hospedagem devem ser tratados separadamente quando a licença for perpétua.

## Checklist de Produção

- [ ] remover `debug=True` do ambiente de produção
- [ ] configurar `JWT_COOKIE_SECURE = True`
- [ ] definir `SECRET_KEY` fixa via variável de ambiente
- [ ] definir `JWT_SECRET_KEY` fixa via variável de ambiente
- [ ] migrar para PostgreSQL
- [ ] colocar atrás de proxy reverso com HTTPS
- [ ] criar rotina de backup do banco
- [ ] revisar arquivos locais que não devem ser versionados, como base SQLite de desenvolvimento
- [ ] adicionar monitoramento e logs de aplicação externos
- [ ] validar rate limiting no login

## Resumo Executivo

O Pronto Ar já cobre operação real de atendimento com separação de perfis, QR Code, manutenção, histórico, relatórios em PDF, notificações por perfil e auditoria administrativa. O README foi consolidado para servir como documento único de entendimento técnico e operacional do projeto.
