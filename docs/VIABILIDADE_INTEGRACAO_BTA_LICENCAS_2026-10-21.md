# Estudo de viabilidade — ProntoAr → BTA Licenças

**Data:** 21/10/2026  
**Natureza:** diagnóstico documental; implementação e migração não autorizadas.  
**ProntoAr analisado:** `Boanerges20297/pro-ar_refrigeracao`, `main` em `4d3a3a37692d90e96fa67dd6cae7477f7d65613e`.  
**BTA analisado:** `Boanerges20297/bta-license-platform`, `main` em `8b485d1cdfaab4ee73fb9ca933ac275548546bec`.  
**Emissor legado:** `Boanerges20297/license_api`, consultado somente para diagnóstico.  
**Fontes de evidência:** código e documentação dos três repositórios; confirmação de arquivos locais por NEXO/STI; inventário read-only dos containers BTA via NEXO. Não houve leitura dos dados efetivos de licenças nos bancos, nem execução de testes de integração.

## Resumo executivo

**Integração tecnicamente viável, com lacunas contratuais e de identidade a resolver.** A ProntoAr pode consumir a BTA License Platform por API S2S autenticada, enquanto o BTA passa a administrar produtos, pacotes, clientes, licenças e permissões. A substituição direta do validador atual seria perigosa: a ProntoAr suporta **licenças perpétuas**, vínculo por **instalação**, flags e limites específicos e continua operando com verificação local de tokens. A BTA usa estado central, modalidades diferentes e snapshots assinados com validade offline limitada.

A proposta é **adaptação progressiva em branch isolada**, com compatibilidade de leitura das chaves legadas durante migração controlada, inventário de contratos e plano explícito de rollback. Não criar duas fontes ativas de autoridade após o corte.

## 1. Inventário dos três componentes

### 1.1 Consumidor local ProntoAr

- `app/utils/license.py`: `get_installation_id`, `decode_license_key`, `evaluate_license`, `activate_license_key`, `revalidate_license`, `get_license_features`, `has_license_feature`, `check_user_limit`.
- `app/models/license.py`: licença local com token, estado, empresa, fingerprint, datas, limites, features e último resultado da validação; `get_license_record` escolhe o primeiro registro.
- `app/config.py`: chave pública Ed25519, caminho do identificador de instalação, 15 dias de alerta, 7 de carência e fallback `itsdangerous` por configuração (padrão desabilitado).
- `app/__init__.py:enforce_license_status`: avaliação a cada requisição e bloqueio centralizado da operação.
- `app/routes/auth.py:login`: impede login de não-administradores quando a licença bloqueia.
- `app/utils/decorators.py:license_feature_required`: protege recursos por plano.
- `app/routes/admin.py` e `app/templates/admin/settings.html`: tela para visualizar, colar e revalidar chave manualmente.
- `tests/test_logic.py`: parte dos testes depende de tokens locais legados e do modelo atual.
- `docs/LICENCIAMENTO_COMERCIAL.md`: distingue planos Basic/Premium, licenças perpétuas/assinatura e manutenção recorrente (não confundir manutenção mensal com direito de uso).

### 1.2 Emissor legado `license_api`

- FastAPI com painel simples de emissão/consulta/revogação.
- `license_api/models.py:IssuedLicense`: `license_id`, empresa, fingerprint, validade, tipo, limites, features, hash do token e revogação.
- `license_api/service.py`: emite payload assinado Ed25519; verifica assinatura + existência no banco + `token_hash` + revogação; aceita `perpetual` ou `subscription`.
- **Limitação:** ProntoAr valida o payload do token localmente, sem consultar a tabela de revogação da API a cada operação; portanto revogação no emissor não é necessariamente reconhecida pelo consumidor antes de troca/revalidação por outro mecanismo.

### 1.3 Plataforma BTA

- Django / PostgreSQL próprio: `Product → Package → PackageVersion → License`, `Customer`, `PackageEntitlement`, `PackageLimit`, `LicenseOverride`, `ServiceClient/ServiceClientKey`, `AuditLog`.
- API S2S: `GET /api/v1/snapshot-key`, `POST /api/v1/licenses/resolve`, `POST /api/v1/licenses/trials/activate`.
- `core/s2s.py`: credencial assimétrica Ed25519 ou RSA-PSS, headers `X-BTA-*`, timestamp, nonce, assinatura e anti-replay.
- `core/snapshots.py`: snapshots Ed25519 com janela offline de até 7 dias, assinados pela BTA e verificáveis localmente.
- Admin independente com VPN/TOTP; backend consumidor usa API S2S, **não** credencial administrativa ou banco BTA.
- Containers `bta-license-api`, `bta-license-db` e `bta-license-admin` constavam **healthy** no inventário read-only do dia; `bta-license-runner` constava `Exited (137)`. Inventário não prova que os endpoints específicos estão acessíveis a partir da ProntoAr ou que o runner é utilizável.

## 2. Compatibilidade de modelos

| Legado ProntoAr | BTA | Ajuste necessário |
|---|---|---|
| Empresa + `instance_fingerprint` | `Customer.customer_key` + observação de `device_key` | `customer_key` identifica titular; observação de device **não** impõe exclusividade de instalação. Precisa política explícita de vínculo, número de instalações e transferência. |
| Planos `basic`/`premium` | `Package` e `PackageVersion` | Criar catálogo específico do produto, versionado. |
| `reports`, `audit`, `maintenance`, `branding`, `email` | `PackageEntitlement`: `enabled`/`preview`/`hidden` | Mapeamento explícito e teste de cada rota. No legado, ausência de `features` concede Premium, comportamento potencialmente permissivo que não pode ser copiado sem análise. |
| `max_users`, `max_admin_users`, `max_secretary_users` | `PackageLimit` e overrides | Preservar significado de `max_users` = funcionários ativos, não todos os perfis. |
| `subscription` com prazo/carência | `paid` + `expires_at` + `grace` | Testar divergências exatas de calendário e expiração. |
| `perpetual` sem vencimento | `paid` possivelmente sem `expires_at` | **Não existe modalidade perpétua canônica explícita na BTA**; exige decisão contratual/modelagem antes de migrar. |
| Token assinado no banco Flask | Resolução S2S + snapshot assinado/cache local | Não equivalem bit a bit; requer adaptador e política de contingência. |
| Status `active`, `expiring`, `expired`, `invalid`, `inactive` | `pending`, `active`, `grace`, `expired`, `suspended`, `revoked`, `validation_required` | Tradução explícita de estados sem confundirem falhas técnicas com licença negada. |

## 3. Riscos classificados

**CRÍTICO — direitos comerciais legados:** assinatura e licença perpétua são compromissos diferentes. A falta de pagamento por manutenção não pode, por si só, extinguir licença perpétua; qualquer mapeamento para a BTA deve conservar esse direito.

**ALTO — bloquear cliente por migração:** login, middleware e decorators dependem diretamente de `evaluate_license()`. Uma mudança abrupta pode impedir acesso a toda operação; precisam adaptador compatível, testes de regressão e rollback.

**ALTO — identidade e anti-compartilhamento:** o fingerprint legado é potencialmente vinculante à instalação; `device_key` na API BTA analisada alimenta telemetria e não é garantia de dispositivo exclusivo. Não derivar `customer_key` do nome da empresa nem criar novas identidades a cada deploy.

**ALTO — concessão involuntária de funcionalidades:** falta de `features` no token local faz `get_license_features` retornar todas as `PREMIUM_FEATURES`; `branding` e `email` têm gating incompleto conforme a documentação. Converter explicitamente para os entitlements BTA.

**ALTO — falha de rede vs. revogação:** a API BTA distingue negação válida, HTTP 401 e HTTP 503; snapshot offline possui prazo e assinatura próprios. O cliente não deve bloquear silenciosamente por timeout, nem manter fallback legado indefinidamente depois do corte.

**MÉDIO — operação/performance:** `enforce_license_status` roda por request; não realizar requisição externa síncrona a cada HTTP. Usar cache local de decisão assinada + sincronização controlada, timeout, telemetria sem segredos e tratamento de concorrência.

**MÉDIO — diferenciação temporal:** testar UTC/horário de Fortaleza, vencimento no dia, carência e validade `offline_valid_until` (inclusive licença perpétua).

**MÉDIO — infraestrutura:** validar canal S2S real entre ProntoAr e BTA, sem expor painel admin ou PostgreSQL; validar health/readiness e condição do runner somente em fase de implantação.

## 4. Arquitetura candidata — NÃO implementada

```text
Navegador ProntoAr
        |
Backend Flask ProntoAr
        |-- Facade de política existente (mesmo contrato interno dos gates)
        |-- Adaptador S2S BTA (credencial privada apenas no backend)
        |       `-- API BTA /api/v1/licenses/resolve
        |                   `-- banco PostgreSQL privado da BTA
        `-- Snapshot assinado validado localmente e cache persistente
```

O painel BTA faz a emissão, alterações e auditoria. A ProntoAr interpreta entitlements e limits específicos do seu domínio. A interface do cliente pode exibir situação/licença/instalação, mas não emitir/revogar licença comercial.

## 5. Sequência recomendada para fase futura

1. **Inventário read-only de licenças existentes** (instalações, contratos, planos, períodos, hashes/IDs, status, limites), preservando backup e sem coletar chave privada; confrontar com os direitos comerciais contratados.
2. **Decisões de domínio BTA:** representação inequívoca de licença perpétua, limite de instalações, troca autorizada, vigência de suporte (separada) e catálogo Basic/Premium.
3. **Teste de contrato S2S** em ambiente de homologação com identidades próprias, rotação de chave, snapshot inválido/expirado, 401/503, replay, retries e falha de rede; sem tocar infraestrutura de produção.
4. **Adaptador ProntoAr** preservando os retornos públicos de `evaluate_license`, os gates, limites, login/admin e comportamento de fluxo.
5. **Migração piloto reversível**, com logs redigidos, comparação de decisões em shadow mode (sem bloquear usuários), testes automatizados e validação funcional.
6. **Corte controlado por instalação**, com autorização explícita, backup, rollback e desativação definitiva do emissor antigo somente após comprovar migração completa.
7. **Revisão de deploy** específica, manual e separada de merge, sem CI/release automático.

## 6. Pendências para decisão antes de codificar

- Inventário real de contratos e instalações ativas ainda **não realizado**.
- Definição comercial de licença perpétua no BTA ainda **não aprovada**.
- Política de instalações concorrentes e transferência ainda **não definida**.
- Conectividade S2S ProntoAr → BTA e migração end-to-end ainda **não testadas**.
- Não há evidência de que as instalações reais já estejam cadastradas na BTA.

**Resultado desta etapa:** documentação apenas; nenhuma alteração no runtime, no emissor legado, nas licenças ou na produção. **Não realizar merge/deploy nem criar pastas auxiliares locais com base neste documento.**
