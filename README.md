# ❄️ Pronto Ar Refrigeração — Sistema de Gestão de Serviços

> Sistema web interno para gestão de clientes, equipamentos, ordens de serviço e manutenção preventiva, com leitura de QR Code em campo.

Desenvolvido por **Boanerges Teixeira de Almeida** — Engenheiro de Software
© 2026 Pronto Ar - Refrigeração

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Tecnologias](#tecnologias)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Executando o Sistema](#executando-o-sistema)
- [Acesso pelo Celular](#acesso-pelo-celular)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Perfis de Usuário](#perfis-de-usuário)
- [Segurança](#segurança)
- [Checklist de Produção](#checklist-de-produção)

---

## Visão Geral

O **Pronto Ar** é um sistema de gestão desenvolvido para empresas de refrigeração e ar-condicionado. Permite controlar o ciclo completo de atendimento: do cadastro do cliente e equipamento até a conclusão da ordem de serviço, passando pelo agendamento de manutenções preventivas.

A identidade visual (logotipo, cores, nome da empresa) é **totalmente personalizável** pelo administrador, diretamente na plataforma.

---

## Funcionalidades

| Módulo | Descrição |
|---|---|
| 🔐 **Autenticação** | Login com JWT em cookie HttpOnly, niveis de permissão (admin/user) |
| 👥 **Clientes** | Cadastro completo com telefone, e-mail e endereço |
| ❄️ **Equipamentos** | Cadastro com QR Code gerado automaticamente |
| 📷 **Scanner QR** | Leitura via câmera do celular — abre o equipamento direto |
| 🔧 **Ordens de Serviço** | Criação, atribuição de técnico, controle financeiro e status |
| 📅 **Manutenção Preventiva** | Agendamentos vinculados a equipamentos |
| 👥 **Funcionários** | Gestão unificada (Técnico, Recepcionista, Admin, Outros) |
| 📊 **Dashboard Admin** | KPIs, receita, performance de técnicos |
| ⚙️ **Configurações** | Logo, cores, nome da empresa — tema 100% personalizável |
| 📱 **Responsividade** | Navbar adaptável com menu hambúrguer para dispositivos móveis |
| 📘 **Tutorial** | Guia embutido passo a passo acessível por botão flutuante |

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| **Backend** | Python 3.x + Flask |
| **Banco de Dados** | SQLite (dev) / PostgreSQL (produção) |
| **ORM** | SQLAlchemy + Flask-Migrate (Alembic) |
| **Autenticação** | Flask-JWT-Extended (cookie HttpOnly) + Flask-Bcrypt |
| **CSRF** | Flask-WTF CSRFProtect |
| **QR Code** | `qrcode[pil]` (geração server-side) |
| **Scanner** | `html5-qrcode` (leitura via câmera no navegador) |
| **Frontend** | Jinja2 + Tailwind CSS (CDN) + Font Awesome + Inter (Google Fonts) |

---

## Pré-requisitos

- Python 3.10 ou superior
- pip
- Virtualenv

---

## Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/pro-ar_refrigeracao.git
cd pro-ar_refrigeracao

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Execute as migrações do banco de dados
flask db upgrade

# 5. (Opcional) Crie o usuário administrador inicial
python seed_admin.py
```

---

## Configuração

As configurações estão em `app/config.py`. Para produção, use **variáveis de ambiente**:

| Variável | Descrição | Padrão |
|---|---|---|
| `SECRET_KEY` | Chave para cookies e CSRF | `os.urandom(32)` ⚠️ |
| `JWT_SECRET_KEY` | Chave para tokens JWT | `os.urandom(32)` ⚠️ |
| `DATABASE_URL` | URI do banco de dados | `sqlite:///pronto_ar.db` |

> ⚠️ **Atenção:** Em produção, defina `SECRET_KEY` e `JWT_SECRET_KEY` como valores fixos via variável de ambiente. O valor aleatório padrão invalida todas as sessões a cada restart do servidor.

```powershell
# Exemplo Windows (PowerShell)
$env:SECRET_KEY = "sua-chave-secreta-longa-e-aleatoria"
$env:JWT_SECRET_KEY = "outra-chave-secreta-longa-e-aleatoria"
```

---

## Executando o Sistema

```bash
# Desenvolvimento
python run.py

# O servidor iniciará em:
# http://127.0.0.1:5000  (localhost)
# http://0.0.0.0:5000    (rede local)
```

Acesse no navegador: **http://localhost:5000**

---

## Acesso pelo Celular

Para acessar pelo celular na **mesma rede Wi-Fi**:

1. Descubra o IP da máquina:
   ```powershell
   ipconfig | findstr "IPv4"
   ```
2. Libere a porta no Firewall do Windows (execute como Administrador):
   ```powershell
   netsh advfirewall firewall add rule name="Flask 5000" dir=in action=allow protocol=TCP localport=5000
   ```
3. Acesse no celular: `http://SEU_IP:5000`

> **Câmera do scanner:** Navegadores mobile bloqueiam `getUserMedia` em HTTP externo.
> Para câmera funcionar no celular, use um túnel HTTPS (ex: [ngrok](https://ngrok.com)) ou sirva via HTTPS.

---

## Estrutura do Projeto

```
pro-ar_refrigeracao/
├── app/
│   ├── __init__.py          # Factory da aplicação Flask
│   ├── config.py            # Configurações (chaves, DB, JWT)
│   ├── models/
│   │   ├── user.py          # Modelo de usuário (Bcrypt)
│   │   ├── client.py        # Clientes
│   │   ├── equipment.py     # Equipamentos + QR Code path
│   │   ├── workorder.py     # Ordens de serviço
│   │   ├── maintenance.py   # Agendamentos
│   │   ├── service.py       # Catálogo de serviços
│   │   └── config.py        # Configurações da empresa (tema, logo)
│   ├── routes/
│   │   ├── auth.py          # Login / Logout
│   │   ├── admin.py         # Dashboard + Configurações
│   │   ├── clients.py       # CRUD Clientes
│   │   ├── equipment.py     # CRUD Equipamentos + Geração QR
│   │   ├── services.py      # Ordens de Serviço
│   │   ├── maintenance.py   # Manutenções
│   │   └── technician.py    # Gestão Unificada de Funcionários (Técnicos, Recepcionistas, etc)
│   ├── templates/
│   │   ├── base.html        # Layout base (navbar, FABs, tutorial)
│   │   ├── auth/            # Login
│   │   ├── admin/           # Dashboard e Configurações
│   │   ├── clients/
│   │   ├── equipment/       # Listagem, cadastro, detalhes + QR
│   │   ├── services/
│   │   ├── maintenance/
│   │   └── technician/
│   └── utils/
│       └── decorators.py    # @roles_required
├── static/
│   └── img/
│       ├── fundo_1.png      # Imagem de fundo da aplicação
│       ├── logo.*           # Logo da empresa (upload pelo admin)
│       └── qrcodes/         # QR Codes gerados automaticamente
├── migrations/              # Alembic migrations
├── run.py                   # Ponto de entrada
├── requirements.txt
└── README.md
```

---

O sistema utiliza um modelo de permissões flexível que separa o nível de acesso da função exercida:

| Nível de Permissão | Acesso | Funções Comuns |
|---|---|---|
| `admin` | Acesso total: Dashboards, Financeiro, Configurações e Gestão de Funcionários | Administrador, Gerente, Proprietário |
| `user` | Acesso operacional: Dashboard Técnico, OS atribuídas, Clientes e Equipamentos | Técnico, Recepcionista, Auxiliar |

### Funções (`job_title`)
As funções são personalizáveis. O sistema vem com padrões (`Técnico`, `Recepcionista`, `Administrador`), mas o administrador pode criar novas funções (ex: `Estagiário`, `Supervisor`) diretamente no cadastro.

---

## Segurança

- ✅ Senhas com **Bcrypt** (hash + salt automático)
- ✅ Sessão via **JWT em cookie HttpOnly** (imune a XSS via JS)
- ✅ **CSRF** protegido em todos os formulários (Flask-WTF)
- ✅ **Zero SQL raw** — apenas ORM SQLAlchemy (imune a SQL Injection)
- ✅ **Jinja2 auto-escape** ativado (imune a XSS nos templates)
- ✅ **Validação de upload** por whitelist de extensão + limite de 2 MB
- ✅ Sessão expira em **30 minutos** de inatividade

---

## Checklist de Produção

Antes de expor o sistema na internet:

- [ ] `debug=False` em `run.py`
- [ ] `JWT_COOKIE_SECURE = True` em `config.py`
- [ ] `SECRET_KEY` e `JWT_SECRET_KEY` fixos via variável de ambiente
- [ ] Servidor atrás de proxy reverso **Nginx** com **HTTPS** (Let's Encrypt)
- [ ] Banco de dados **PostgreSQL** (SQLite não suporta acesso concorrente)
- [ ] Rate limiting no endpoint de login (`flask-limiter`)
- [ ] Backup automático do banco de dados

---

*Pronto Ar Refrigeração — Sistema desenvolvido com ❤️ por Boanerges Teixeira de Almeida*
