# Pronto-Ar — Remediação da auditoria de qualidade
Data: 2026-11-06 (Fortaleza)
Ambiente: STI01, branch `test/coverage-all-modules-20261106`.
Base da aplicação: commit `cdb4442`.

## Resultado
**Antes:** 98 aprovados, 17 falhas, cobertura 64%.
**Após correções:** 106 aprovados, 0 falhas, 366 subtestes aprovados, 62 avisos e cobertura 64%.
Comando: `.\.venv\Scripts\python.exe -W ignore -m pytest tests -q --disable-warnings --tb=short --cov=app --cov-branch --cov-report=term --cov-report=json:tests/.results/coverage-remediation.json --junitxml=tests/.results/junit-remediation.xml`.

## Correções aplicadas
- Cadastro de OS: valida existência e coerência de todos os FKs antes do `flush`, rejeita valores fora do limite inteiro, datas inválidas e preços NaN/Infinity; tratamento de erro SQL com rollback.
- Duplicidade de OS: GET do formulário e POST por data compartilham contrato JSON com `exists` e `duplicate`; GET exige autenticação.
- Secretaria: `service_id` passou a integrar a OS; seleção obrigatória no formulário e fallback apenas quando existe exatamente um serviço; verifica técnico ativo, cliente/equipamento, data e persiste atomicamente.
- Financeiro: valores e datas são validados nas operações de criação e edição; valores não finitos rejeitados.
- Equipamentos: intervalo de manutenção validado antes de gravação, cliente existente.
- Despesas: quantidade zero não é convertida silenciosamente para uma unidade.
- Exportação da auditoria: CSV em BytesIO, UTF-8 com BOM, compatível com send_file.
- Login de usuário não identificado: `audit_log.user_id` passa a aceitar NULL; mantém a FK; migração Alembic `b6f3c91a2d08`.
- VAPID: 503 quando sem configuração é comportamento esperado; teste verifica modo sem configuração e resposta 200 configurada.

## Evidências
- `tests/.results/remediation-final.log`
- `tests/.results/junit-remediation.xml`
- `tests/.results/coverage-remediation.json`
- `tests/test_audit_migration_contract.py`: upgrade de schema validado em SQLite temporário.
- `git diff --check` e `compileall` sem erro na inspeção local.

## Limites e publicação
Cobertura **64%** não significa garantia da aplicação inteira. Baixa cobertura em portal de clientes (28%), técnicos (45%), e notificações (29%); exigem novas suítes, especialmente PostgreSQL isolado, UI e concorrência.

**Não publicar automaticamente.** A migração de auditoria altera esquema de banco. Antes de produção, verificar a revisão Alembic ativa na VPS, preparar backup, ensaiar migração e revisar a sequência de deploy. Não usar `db.create_all` como substituto da migração. A main remota e a VPS de produção não foram modificadas durante esta remediação.
