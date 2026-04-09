# Licenciamento Comercial da BTA Solucoes em Desenvolvimento de Software

Este documento define como vender, operar e comunicar os modelos de licenca administrados pela BTA Solucoes em Desenvolvimento de Software sem misturar direito de uso do software com servicos continuos da equipe responsavel pela operacao.

## Objetivo

O modelo de licenciamento da BTA foi desenhado para separar tres camadas diferentes:

1. direito de uso do software;
2. funcionalidades contratadas;
3. servicos recorrentes de suporte, hospedagem, backup e operacao.

Essa separacao evita ambiguidade comercial e reduz conflito no momento de cobranca, renovacao, upgrade de plano e inadimplencia.

## Principios Comerciais

### Licenca nao e cessao de codigo-fonte

- o cliente compra o direito de uso do sistema;
- o cliente nao recebe propriedade intelectual do produto;
- o cliente nao recebe codigo-fonte;
- o cliente nao pode revender, sublicenciar ou redistribuir o sistema sem autorizacao contratual.

### Servico recorrente nao deve ser confundido com direito de uso

Quando existir licenca perpetua, o pagamento mensal nao deve ser apresentado como aluguel do software. Ele deve ser apresentado como contrato de servicos recorrentes.

Exemplos de servicos recorrentes:

- suporte tecnico;
- backup gerenciado;
- hospedagem administrada;
- armazenamento gerenciado;
- atualizacoes corretivas e evolutivas;
- monitoramento;
- atendimento operacional da equipe.

### Regras de bloqueio devem respeitar o modelo contratado

- licenca por assinatura: pode bloquear o uso do sistema quando expirar e terminar a carencia;
- licenca perpetua: nao deve bloquear o uso principal por falta de mensalidade de manutencao;
- servicos recorrentes podem ser suspensos por inadimplencia, conforme contrato e infraestrutura contratada.

## Arquitetura Comercial Recomendada

### Papel do sistema principal

O sistema principal deve funcionar como painel da licenca da instalacao do cliente. Nele, o cliente final deve:

- visualizar o ID da instalacao;
- visualizar o status da licenca;
- colar a chave recebida;
- revalidar a licenca salva localmente.

O cliente final nao deve emitir, revogar ou administrar licencas comerciais.

### Papel da license_api

A `license_api` deve funcionar como backoffice interno da operacao comercial e tecnica. Ela deve ser usada pela sua equipe para:

- emitir licencas novas;
- renovar assinaturas;
- trocar instalacao autorizada;
- revogar licencas em caso de fraude, cancelamento ou troca contratual;
- consultar historico das licencas emitidas.

## Modelos Comerciais Recomendados

### Modelo A: Licenca perpetua + manutencao recorrente

Indicado para cliente que quer comprar o direito de uso e aceitar um contrato mensal separado de servicos.

#### Como comunicar

- pagamento inicial: licenca de uso da versao contratada;
- mensalidade: suporte, operacao, backup, armazenamento, hospedagem ou manutencao;
- sem codigo-fonte;
- sem direito de copia ou revenda.

#### Regra operacional

- o uso do software continua valido enquanto a licenca perpetua estiver integra e vinculada corretamente a instalacao;
- se a manutencao mensal vencer, nao se deve bloquear a operacao principal por esse motivo;
- o que pode ser suspenso e o servico continuo contratado.

#### O que pode ser suspenso por inadimplencia da manutencao

- suporte tecnico;
- atualizacoes;
- backup gerenciado;
- armazenamento administrado por sua equipe;
- monitoramento;
- hospedagem, quando o ambiente for seu.

#### Observacao importante

Se a aplicacao estiver hospedada em infraestrutura sua, a suspensao da hospedagem impacta o acesso porque o ambiente inteiro deixa de estar disponivel. Isso nao significa que a licenca perpetua deixou de existir. Significa apenas que o servico gerenciado foi suspenso. Contratualmente, isso precisa estar claro.

### Modelo B: Assinatura

Indicado para novos clientes quando voce quer receita recorrente simples, previsivel e com menos discussao contratual.

#### Como comunicar

- o cliente paga pelo direito de uso durante a vigencia da assinatura;
- suporte, atualizacoes e operacao podem estar embutidos no mesmo valor;
- ao vencer a assinatura, o sistema entra em aviso, carencia e depois bloqueio.

#### Regra operacional

- a licenca e emitida como `subscription`;
- o sistema calcula vencimento e carencia;
- apos a carencia, o uso operacional pode ser bloqueado.

## Matriz de Funcionalidades por Plano

As funcionalidades devem ser separadas em plano funcional e modelo de cobranca. Em outras palavras:

- `Basic` e `Premium` definem o que o cliente pode usar;
- `Perpetua` e `Assinatura` definem como o cliente paga e como a vigencia e tratada.

### Funcionalidades base do produto

Estas funcionalidades compoem o nucleo operacional do sistema e devem estar disponiveis em qualquer contrato Basic ou Premium:

- autenticacao e sessao;
- dashboards por perfil;
- cadastro de clientes;
- cadastro e consulta de equipamentos;
- QR Code por equipamento;
- ordens de servico e historico operacional;
- gestao de usuarios;
- limites de usuarios conforme licenca;
- ativacao e consulta da propria licenca.

### Funcionalidades Premium

Estas funcionalidades representam o pacote ampliado do produto:

- `reports`: relatorios gerenciais, financeiros, por cliente e por servico;
- `audit`: consulta e exportacao de logs de auditoria;
- `maintenance`: agenda e baixa de manutencao preventiva;
- `branding`: personalizacao visual ampliada da identidade do sistema;
- `email`: configuracao SMTP e recuperacao de senha por e-mail.

### Tabela comercial recomendada

| Recurso | Basic | Premium |
|---|---|---|
| Dashboards por perfil | Sim | Sim |
| Clientes | Sim | Sim |
| Equipamentos | Sim | Sim |
| QR Code | Sim | Sim |
| Ordens de servico | Sim | Sim |
| Gestao de usuarios | Sim | Sim |
| Limites por licenca | Sim | Sim |
| Relatorios gerenciais | Nao | Sim |
| Auditoria administrativa | Nao | Sim |
| Manutencao preventiva | Nao | Sim |
| Personalizacao visual ampliada | Nao | Sim |
| Recuperacao por e-mail / SMTP | Nao | Sim |

### Estado tecnico atual

No estado atual do sistema, o bloqueio/licenciamento ja esta efetivamente aplicado para:

- `reports`;
- `audit`;
- `maintenance`.

Os flags `branding` e `email` ja existem no modelo comercial e na emissao da licenca, mas devem ser tratados como escopo comercial contratado ate que o gating integral dessas areas esteja concluido na interface e nas rotas relacionadas.

## Sugestao de Precos

Os valores abaixo sao referenciais de posicionamento inicial. Eles nao sao tabela fixa, mas um ponto de partida coerente para produto B2B pequeno/medio no seu estagio atual.

### Precos recomendados para novos contratos

| Oferta | Preco sugerido | Observacao |
|---|---|---|
| Licenca Perpetua Basic | R$ 2.490 | direito de uso sem codigo-fonte |
| Licenca Perpetua Premium | R$ 4.490 | inclui os modulos premium |
| Assinatura Basic | R$ 297/mes | uso continuo enquanto vigente |
| Assinatura Premium | R$ 597/mes | uso continuo com modulos premium |
| Implantacao inicial | R$ 600 a R$ 1.500 | migracao, parametrizacao e treinamento |

### Servicos recorrentes sugeridos

| Servico | Preco sugerido | Observacao |
|---|---|---|
| Manutencao gerenciada Basic | R$ 197/mes | suporte, backup e operacao basica |
| Manutencao gerenciada Premium | R$ 297/mes | suporte ampliado e operacao premium |
| Hospedagem/armazenamento sob sua gestao | embutir ou cobrar a parte | depende do custo mensal real |

### Como tratar o cliente legado de R$ 2.000 + R$ 200/mes

O contrato citado e comercialmente viavel, desde que seja descrito assim:

- `R$ 2.000`: licenca de uso da versao contratada, sem codigo-fonte;
- `R$ 200/mes`: manutencao gerenciada, suporte, backup e administracao do armazenamento.

Esse cliente pode permanecer como contrato legado. Nao e obrigatorio reprecificar de imediato. O mais importante e documentar corretamente que o mensal nao compra o direito de uso, e sim os servicos continuos.

### Quando alterar a precificacao do perpetuo

Faz sentido rever o perpetuo quando:

- o cliente quiser modulos premium;
- o cliente exigir hospedagem e operacao sob sua responsabilidade;
- o custo de suporte mensal estiver maior do que o ticket atual suporta;
- a base de funcionalidades do produto tiver crescido significativamente.

## Regras Comerciais de Inadimplencia

### Para licenca perpetua

- nao bloquear o uso do sistema apenas por atraso da manutencao;
- suspender servicos recorrentes conforme contrato;
- interromper atualizacoes e suporte ate regularizacao;
- se a infraestrutura for sua, permitir suspensao da hospedagem apos aviso formal e prazo contratual.

### Para assinatura

- avisar antes do vencimento;
- manter carencia curta e clara;
- bloquear operacao apos o fim da carencia;
- oferecer renovacao ou upgrade com emissao de nova licenca.

## Quando Emitir Nova Licenca

Deve ser emitida nova licenca quando ocorrer:

- nova venda;
- renovacao de assinatura;
- upgrade de Basic para Premium;
- aumento de limites de usuarios;
- troca autorizada de instalacao ou servidor;
- mudanca de empresa licenciada;
- revogacao e substituicao de chave comprometida.

Nao e necessario emitir nova licenca apenas porque a equipe executou suporte tecnico comum, desde que o contrato e os limites permaneçam os mesmos.

## Fluxo Operacional Recomendado

### Nova venda

1. instalar ou preparar o ambiente do cliente;
2. identificar o `ID da instalacao` no sistema principal;
3. definir modelo comercial: perpetua ou assinatura;
4. definir plano funcional: Basic ou Premium;
5. definir limites de usuarios;
6. emitir a licenca no backoffice da `license_api`;
7. entregar a chave ao cliente ou ativar junto com ele;
8. registrar o contrato comercial correspondente.

### Renovacao de assinatura

1. confirmar pagamento;
2. emitir nova licenca com novo periodo;
3. substituir a chave na instalacao atual ou orientar o cliente;
4. registrar vigencia renovada.

### Upgrade de plano

1. confirmar valor do upgrade;
2. emitir nova licenca com `features` atualizadas;
3. ativar a nova chave;
4. validar se os modulos premium esperados foram liberados.

### Troca autorizada de instalacao

1. coletar novo `ID da instalacao`;
2. revogar ou aposentar a chave anterior, conforme politica interna;
3. emitir nova licenca vinculada ao novo ambiente;
4. registrar o motivo da troca.

## Posicionamento Recomendado Para Venda

### Oferta principal para novos clientes

Use assinatura como oferta padrao para novos contratos. Ela e mais simples de vender, operar e cobrar.

### Oferta alternativa para clientes tradicionais

Use licenca perpetua apenas para quem explicitamente quer comprar o direito de uso. Nesse caso, venda a manutencao recorrente como servico separado.

### Regra pratica de proposta comercial

- cliente quer previsibilidade e tudo incluso: assinatura;
- cliente quer comprar o sistema e manter controle do ativo: perpetua;
- cliente quer poucos modulos e entrada menor: Basic;
- cliente quer gestao, indicadores, manutencao e auditoria: Premium.

## Clausulas que Devem Ficar Claras no Contrato

- licenca de uso sem codigo-fonte;
- numero de instalacoes permitidas;
- limites de usuarios por perfil;
- plano contratado e modulos inclusos;
- politica de renovacao e inadimplencia;
- politica de troca de servidor/instalacao;
- escopo da manutencao mensal;
- escopo de hospedagem e armazenamento, quando houver;
- tempo de resposta de suporte, se houver SLA.

## Resumo Executivo

O desenho comercial mais seguro para a BTA e:

- manter `license_api` como backoffice interno;
- deixar o cliente final apenas ativar e consultar a propria licenca no sistema principal;
- usar `Basic` e `Premium` para definir funcionalidades;
- usar `Perpetua` e `Assinatura` para definir a regra financeira e de vigencia;
- separar claramente mensalidade de servico da venda do direito de uso quando o contrato for perpetuo.