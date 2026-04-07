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
- Checklist de Produção

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
│       └── notifications.py
├── instance/
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
- Flask-WTF 1.2.1
- SQLAlchemy 2.0.36
- Werkzeug 3.1.3

### Utilitários adicionais

- python-dotenv 1.0.1
- qrcode[pil] 8.2
- Pillow 12.2.0
- python-dateutil 2.9.0.post0
- reportlab 4.0.9

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
| `JWT_SECRET_KEY` | chave JWT | gerada aleatoriamente |

### Observações de configuração

- `JWT_ACCESS_TOKEN_EXPIRES = 1800` define sessão de 30 minutos.
- `JWT_TOKEN_LOCATION = ['cookies']` usa cookie como transporte.
- `JWT_COOKIE_SECURE = False` no ambiente atual; em produção deve ser `True` com HTTPS.
- `JWT_COOKIE_CSRF_PROTECT = False` porque o projeto usa CSRF do Flask-WTF nos formulários.

Exemplo em PowerShell:

```powershell
$env:SECRET_KEY = "chave-secreta-flask"
$env:JWT_SECRET_KEY = "chave-secreta-jwt"
$env:DATABASE_URL = "sqlite:///pronto_ar.db"
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

- criação da tabela `audit_log`.

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
- cria usuários base;
- cria clientes e equipamentos de exemplo;
- cria catálogo de serviços;
- gera ordens de serviço de demonstração com datas aleatórias.

Credenciais de seed informadas pelo próprio script:

- admin: `admin@prontoar.com` / `admin123`
- técnico: `carlos@prontoar.com` / `tech1234`

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
| `/admin/audit-logs` | consulta de auditoria |
| `/secretary/dashboard` | operação administrativa restrita |
| `/secretary/workorders/pending` | fila de ordens pendentes/em andamento |
| `/services` | listagem agrupada de ordens por cliente |
| `/services/history` | histórico completo com filtros |
| `/maintenance` | agenda preventiva |
| `/equipment/view/<serial>` | detalhe do equipamento via código/QR |

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
- README é a documentação única do projeto no estado atual.

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
