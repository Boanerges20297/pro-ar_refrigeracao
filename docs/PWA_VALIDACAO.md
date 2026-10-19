# PWA do ProntoAr — validação isolada

Branch: `feature/pwa-instalavel-seguro` (derivada da `main`).

## Regra de segurança

O PWA é opt-in. `PWA_ENABLED` não configurado equivale a `false`.
Não existe deploy automático dessa branch. O workflow de produção só publica `main`,
mediante confirmação `DEPLOY` e CI verde da `main`.

O service worker atende somente navegações GET online (sem cache de respostas).
Em falha de rede mostra uma tela pública offline já armazenada; não há armazenamento
de dashboards, APIs, JWT, dados do cliente, OS, fotos ou documentos. O cache recebe
exclusivamente `/static/pwa/offline.html`. Sem fila de sincronização ou push.

## Homologação

1. Implantar a branch em instância **separada** (domínio HTTPS próprio, processo, banco e
   credenciais de testes próprios). Não apontar uma segunda instância ao banco de produção.
2. Habilitar **apenas nessa instância** `PWA_ENABLED=1` no ambiente do serviço.
3. No Chrome Android, abrir login e usar "Instalar aplicativo" pelo menu do navegador.
   No Safari iOS, usar Compartilhar > Adicionar à Tela de Início.
4. Verificar no DevTools > Application > Manifest o nome ProntoAr e ícones 192/512.
5. Verificar em Application > Service Workers `/sw.js` com escopo `/`.
6. Autenticar, abrir uma ordem de serviço e executar logout. Confirmar o comportamento
   normal, sem congelamento de informações e sem precisar autenticar duas vezes.
7. Com PWA aberto e internet desligada, tentar navegar: deve aparecer somente a
   mensagem pública "Sem conexão". Reconectar e tentar novamente.
8. Em DevTools > Application > Cache Storage, conferir que existe apenas o conteúdo
   público `/static/pwa/offline.html`; não deve haver HTML autenticado ou respostas de API.
9. Executar `python -m pytest -q tests/test_pwa.py` e toda a suíte de regressão.
10. Antes de aprovar produção, revisar permissões, HTTPS e evidência do CI da branch.

## Reversão

Alterar `PWA_ENABLED=0` desativa o manifesto/registro nas páginas e o caminho
`/sw.js` passa a responder com o worker que desregistra o anterior e limpa o cache
quando o navegador buscar uma atualização. Clientes já instalados podem exigir
reabertura e acesso à internet para receber a atualização; nenhuma resposta de
conteúdo autenticado está no cache.

Sem autorização para merge, não modificar `main` nem executar o deploy manual.
