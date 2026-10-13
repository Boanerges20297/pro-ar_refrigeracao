# Arquitetura do Pronto Ar Refrigeração

> Documento vivo de referência arquitetural. Antes de alterar um fluxo relevante, localizar seu impacto em rota, regra/utilitário, modelo, template, migração, permissão e licenciamento.

## 1. Visão arquitetural

O Pronto Ar é um **monólito modular Flask**, com renderização server-side por Jinja2. A aplicação organiza responsabilidades por Blueprints, modelos SQLAlchemy, utilitários transversais e templates por domínio.

Em produção, o fluxo principal é:

```text
Usuário / Navegador
        |
      HTTPS
        |
        v
     Nginx
        |
        v
    Gunicorn
        |
        v
 Flask Application Factory
    app/__init__.py
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
   Blueprints               Utils                Jinja UI
        |                      |                      |
        +----------------------+----------------------+
                               |
                               v
                        SQLAlchemy ORM
                               |
                               v
                          PostgreSQL
```

SQLite continua suportado pelo código para cenários locais, enquanto a implantação documentada em produção utiliza PostgreSQL.

## 2. Bootstrap e infraestrutura interna

O ponto central da aplicação é `create_app()` em `app/__init__.py`.

Responsabilidades do bootstrap:

- carregar configurações;
- inicializar SQLAlchemy;
- inicializar Alembic/Flask-Migrate;
- configurar JWT;
- configurar Bcrypt;
- configurar Flask-Limiter;
- ativar CSRF;
- aplicar ProxyFix quando configurado;
- preparar diretórios persistentes;
- validar contexto de autenticação;
- aplicar política same-origin para operações mutáveis;
- avaliar o estado da licença;
- injetar usuário, configuração, alertas e licença nos templates;
- registrar comandos de auditoria;
- registrar Blueprints.

Isso torna `app/__init__.py` uma fronteira crítica: mudanças nele podem afetar praticamente toda a aplicação.

## 3. Camadas lógicas

### 3.1 Entrada HTTP

Local: `app/routes/`

As rotas recebem requests, validam acesso, coordenam regras de negócio e selecionam respostas/templates.

Blueprints registrados atualmente:

| Blueprint | Prefixo | Responsabilidade |
|---|---|---|
| `main` | `/` | entrada e navegação geral |
| `auth` | `/auth` | autenticação e recuperação de acesso |
| `admin` | `/admin` | administração geral |
| `secretary` | `/secretary` | operação administrativa restrita |
| `technician` | `/tech` | operação do técnico |
| `clients` | `/clients` | clientes |
| `equipment` | `/equipment` | equipamentos e QR Code |
| `services` | `/services` | ordens e serviços |
| `maintenance` | `/maintenance` | manutenção preventiva |
| `reports` | `/reports` | relatórios |
| `finance` | `/admin/finance` | gestão financeira |
| `client_portal` | próprio | portal externo do cliente |

### 3.2 Regras e serviços transversais

Local: `app/utils/`

Principais responsabilidades:

- segurança e fingerprint de sessão;
- decorators de autorização;
- auditoria;
- licenciamento;
- notificações;
- imagens e fotos de OS;
- e-mail;
- tratamento textual.

Esses módulos devem concentrar comportamento reutilizável e evitar duplicação de regra entre Blueprints.

### 3.3 Persistência

Local: `app/models/`

Modelos registrados no ORM:

- `User`
- `Client`
- `Equipment`
- `ServiceCatalog`
- `WorkOrder`
- `WorkOrderExpense`
- `AppConfig`
- `MaintenanceSchedule`
- `AuditLog`
- `License`
- `FinancialCategory`
- `FinancialTransaction`

Evoluções de schema devem ser feitas por migrações Alembic em `migrations/versions/`.

### 3.4 Apresentação

Local: `app/templates/`

A interface é renderizada no servidor com Jinja2. `base.html` funciona como base visual e os módulos mantêm templates próprios.

Tecnologias de interface documentadas:

- Jinja2;
- Tailwind CSS via CDN;
- Font Awesome;
- HTML5 QRCode;
- JavaScript no próprio frontend para interações específicas.

## 4. Mapa dos domínios

```text
                         IDENTIDADE
                            User
                             |
             +---------------+---------------+
             |               |               |
           Admin         Secretary       Technician
             |               |               |
             +---------------+---------------+
                             |
                             v
CLIENTE --------------> EQUIPAMENTO
  |                         |
  |                         +------> MaintenanceSchedule
  |                         |
  +-------------------------+------> WorkOrder
                                      |
                         +------------+-------------+
                         |                          |
                         v                          v
                  ServiceCatalog            WorkOrderExpense
                         |                          |
                         +------------+-------------+
                                      |
                                      v
                                  FINANCEIRO
                             FinancialTransaction
                             FinancialCategory

TRANSVERSAIS:
AuditLog | AppConfig | License | Notifications | Security
```

## 5. Núcleo operacional

O agregado operacional principal pode ser entendido como:

```text
Client
  └── Equipment
        ├── MaintenanceSchedule
        └── WorkOrder
              ├── ServiceCatalog
              ├── Technician/User
              ├── fotos antes/depois
              └── WorkOrderExpense
```

O fluxo de maior impacto funcional é:

```text
Cliente
  -> Equipamento
      -> Ordem de Serviço
          -> Técnico
          -> Agendamento
          -> Execução
          -> Conclusão
          -> Histórico
          -> Reflexos financeiros
```

Alterações em `WorkOrder` devem ser tratadas como de alto impacto porque atravessam operação, técnico, cliente, equipamento, relatórios, financeiro e auditoria.

## 6. Perfis e autorização

O campo principal de autorização é `permission_level`.

### Admin

Acesso administrativo amplo, incluindo gestão, configurações, financeiro, relatórios, funcionários e auditoria, sujeito também às features da licença.

### Secretary

Perfil administrativo operacional. Pode trabalhar com clientes, equipamentos, agendamentos, manutenção e conclusão de OS dentro das regras do sistema, sem receber automaticamente privilégios administrativos sensíveis.

### User / Técnico

Perfil de campo, orientado principalmente às ordens atribuídas e aos próprios dados operacionais.

### Regra arquitetural

Autenticação e autorização são conceitos diferentes.

Uma rota autenticada não deve ser considerada autorizada apenas porque existe um JWT válido. Toda operação sensível deve validar também perfil, propriedade/vínculo do recurso e, quando aplicável, feature da licença.

## 7. Segurança

O sistema possui múltiplas camadas complementares:

```text
Request
  |
  +-> Same-Origin para mutações
  |
  +-> JWT em cookie
  |
  +-> usuário ativo
  |
  +-> permission_level coerente com JWT
  |
  +-> versão da senha
  |
  +-> nonce da sessão (quando habilitado)
  |
  +-> fingerprint de User-Agent (quando habilitado)
  |
  +-> CSRF
  |
  +-> Rate Limit
  |
  +-> autorização da rota/recurso
  |
  +-> licença / feature flag
  v
Operação permitida
```

Fotos de ordens de serviço são tratadas como conteúdo protegido e não devem ser expostas simplesmente como arquivos públicos em `/static`.

## 8. Licenciamento

O licenciamento é uma preocupação transversal e não apenas uma tela administrativa.

```text
License local
     |
     v
evaluate_license()
     |
     +--> estado da instalação
     |
     +--> bloqueio global quando aplicável
     |
     +--> feature flags
              |
              +--> reports
              +--> audit
              +--> maintenance
              +--> branding
              +--> email
```

O sistema principal é consumidor/validador da licença da instalação. A `license_api` é o backoffice separado responsável pela operação comercial de emissão e administração das licenças.

Basic/Premium definem funcionalidades. Perpétua/Assinatura definem vigência e modelo comercial.

## 9. Auditoria

`AuditLog` registra ações relevantes e contexto operacional, incluindo usuário, recurso, status, IP, User-Agent, detalhes e timestamp.

A auditoria deve ser considerada transversal aos fluxos críticos, especialmente:

- autenticação;
- alteração de usuários;
- alteração de clientes/equipamentos;
- ordens de serviço;
- configurações;
- operações administrativas.

A retenção operacional documentada é de 7 dias.

## 10. Manutenção preventiva

```text
Equipment
    |
    v
MaintenanceSchedule
    |
    +--> próxima manutenção
    +--> última manutenção
    +--> descrição
    +--> ativo/inativo
    |
    v
Alertas / acompanhamento / baixa
```

Esse domínio está sujeito ao feature gating de licenciamento.

## 11. QR Code e equipamentos

```text
Equipment
   |
   +--> serial_number
   +--> id interno
   +--> QR Code
            |
            v
       Scanner mobile
            |
            v
     resolução do equipamento
            |
            v
      detalhe + histórico
```

A leitura pode reconhecer série, ID interno ou URL completa produzida pelo sistema.

## 12. Financeiro

O código atual já possui domínio financeiro além do mapa original do README.

Componentes principais:

- `FinancialCategory`;
- `FinancialTransaction`;
- `WorkOrderExpense`;
- Blueprint `finance` sob `/admin/finance`;
- valores financeiros existentes em `WorkOrder`.

Consequentemente, alterações de valores, pagamentos, conclusão de OS ou despesas devem ser verificadas também contra o módulo financeiro e relatórios.

## 13. Portal do cliente

O código atual registra `client_portal_bp`, constituindo uma fronteira adicional em relação aos perfis internos.

Regra de projeto: qualquer evolução do portal deve manter separação explícita entre acesso do cliente e acesso administrativo/técnico, evitando reutilizar permissões internas como atalho de autorização externa.

## 14. Persistência de arquivos

Dados persistentes não devem depender do checkout Git.

Especial atenção para:

- `instance/`;
- `uploads/`;
- `keys/`;
- `.env`;
- fotos de OS;
- material de QR Code quando persistido.

Atualizações de código não devem sobrescrever esses dados.

## 15. Produção

Arquitetura operacional documentada:

```text
Internet
   |
 HTTPS
   |
 Nginx
   |
 Gunicorn
   |
 Flask
   |
 PostgreSQL
```

Aplicação:

```text
/var/www/pro-ar_refrigeracao
```

Serviço:

```text
pro-ar.service
```

O processo de atualização deve distinguir claramente dois cenários:

1. **somente código**: pull/restart, sem migration ou seed;
2. **mudança de schema/dependência**: backup, atualização, dependências, Alembic e restart controlado.

Nunca executar `seed.py` automaticamente numa atualização de rotina.

## 16. Matriz de impacto para mudanças

Antes de implementar uma alteração relevante, conferir:

| Camada | Pergunta |
|---|---|
| Rota | Qual Blueprint recebe a operação? |
| Autorização | Quais perfis podem executar/ver? |
| Regra | Existe utilitário ou regra transversal afetada? |
| Modelo | Há mudança de entidade, relação ou estado? |
| Banco | Precisa de migration Alembic? |
| Template | Quais telas exibem ou alteram o dado? |
| Auditoria | A ação precisa ser registrada? |
| Notificação | A mudança gera ou altera alerta? |
| Licença | O recurso depende de feature/limite contratado? |
| Financeiro | Há impacto em valor, pagamento ou despesa? |
| Portal | O cliente externo enxerga esse dado? |
| Segurança | Existe risco de acesso indevido ou IDOR? |
| Produção | Exige dependência, restart ou procedimento especial? |

## 17. Classificação de risco

### Alto impacto

- autenticação e sessão;
- `app/__init__.py`;
- `User` e permissões;
- `WorkOrder`;
- licenciamento;
- financeiro;
- upload/fotos;
- migrações;
- acesso do portal do cliente.

### Médio impacto

- clientes;
- equipamentos;
- manutenção;
- relatórios;
- notificações;
- configurações visuais.

### Baixo impacto relativo

- alterações puramente visuais sem mudança de dados, permissão ou fluxo.

Mesmo alterações visuais devem ser verificadas nos diferentes perfis quando o template for compartilhado.

## 18. Regra de trabalho para evolução

Para cada demanda futura, usar esta sequência:

```text
1. Identificar o fluxo afetado
2. Localizar Blueprint/rota
3. Identificar modelos envolvidos
4. Conferir autorização por perfil
5. Conferir feature/limite de licença
6. Mapear templates envolvidos
7. Avaliar migration
8. Avaliar auditoria/notificações
9. Implementar
10. Testar o fluxo principal
11. Testar perfis limítrofes
12. Revisar impacto em produção
13. Atualizar esta documentação se a arquitetura mudou
```

## 19. Dívidas/documentação a acompanhar

A estrutura real já evoluiu além de partes do README. Este documento passa a registrar explicitamente elementos existentes no código atual, como:

- módulo financeiro;
- `WorkOrderExpense`;
- `FinancialCategory`;
- `FinancialTransaction`;
- portal do cliente;
- endurecimento da sessão/autenticação;
- licenciamento transversal.

Quando houver divergência entre documentação e implementação, a divergência deve ser investigada e corrigida; não presumir automaticamente que uma das duas representa a regra de negócio desejada.

---

**Referência:** arquitetura levantada sobre a branch `main` do repositório `Boanerges20297/pro-ar_refrigeracao` em 02/09/2026.