# Simulacao de Arquitetura em Hospedagem Compartilhada

Este documento simula o cenário em que a BTA insiste em usar hospedagem compartilhada para o sistema principal, mesmo sabendo que o desenho ideal do licenciamento desacoplado foi pensado para VPS.

O objetivo aqui nao e recomendar esse caminho como melhor pratica. O objetivo e mostrar a forma menos arriscada de fazer isso funcionar com o menor custo possivel.

## Resposta Curta

Se voce insistir em hospedagem compartilhada, a arquitetura completa com:

- app principal;
- `license_api` separada;
- processos persistentes independentes;
- proxy reverso;
- portas internas dedicadas;

nao deve ser tratada como confiavel.

O caminho viavel e um desenho reduzido:

1. hospedar apenas o sistema principal na hospedagem compartilhada;
2. manter a `license_api` fora da hospedagem compartilhada;
3. validar a licenca localmente no sistema principal com a chave publica;
4. emitir licencas no ambiente administrativo da BTA, nao no mesmo host do cliente.

## O Que Nao Deve Ser Tentado em Hospedagem Compartilhada

Evite insistir nestes itens em hospedagem compartilhada tradicional:

- rodar Gunicorn e Uvicorn como servicos seus;
- depender de `systemd`;
- abrir portas internas como `8000` e `8010`;
- manter `license_api` publicada como segundo servico Python persistente;
- assumir que voce podera configurar `nginx` livremente;
- guardar a chave privada do licenciamento no mesmo ambiente compartilhado do cliente.

Mesmo quando o provedor oferece "suporte a Python", quase sempre isso significa um fluxo limitado, dependente do painel do provedor e sem liberdade real de arquitetura.

## Arquitetura Minima Viavel em Compartilhada

### O que fica na hospedagem compartilhada

- o sistema principal do cliente;
- a chave publica para validacao local;
- o banco da aplicacao do cliente;
- uploads e arquivos do proprio cliente.

### O que fica fora da hospedagem compartilhada

- a `license_api`;
- a chave privada de emissao;
- o painel de administracao de licencas;
- o banco das licencas emitidas.

## Desenho Recomendado Nesse Cenário

### Camada 1: ambiente do cliente

Na hospedagem compartilhada do cliente fica apenas o sistema principal.

Responsabilidades:

- autenticar usuarios;
- operar clientes, equipamentos, servicos e modulos do produto;
- mostrar o ID da instalacao;
- receber a chave da licenca;
- validar a chave localmente com a chave publica;
- aplicar features e limites da licenca.

### Camada 2: ambiente administrativo da BTA

Fora da hospedagem compartilhada fica o licenciamento central.

Responsabilidades:

- emitir licencas;
- renovar licencas;
- revogar licencas;
- registrar historico das emissoes;
- guardar a chave privada.

Esse ambiente pode ser:

- uma VPS barata;
- uma maquina local da BTA com rotina operacional controlada;
- um ambiente administrativo separado do cliente.

## Fluxo Operacional Nessa Simulacao

### Venda inicial

1. a BTA publica o sistema principal na hospedagem compartilhada do cliente;
2. o sistema gera o `ID da instalacao`;
3. o cliente informa esse ID para a BTA;
4. a BTA emite a licenca fora da hospedagem compartilhada;
5. a BTA envia a chave para o cliente;
6. o cliente cola a chave no painel administrativo do sistema principal.

### Renovacao

1. a BTA confirma pagamento;
2. emite nova licenca fora da hospedagem compartilhada;
3. envia a nova chave ao cliente;
4. o cliente ativa ou renova a chave no sistema principal.

### Upgrade de plano

1. a BTA redefine features e limites;
2. emite nova licenca;
3. o cliente substitui a chave;
4. o sistema passa a liberar os modulos contratados.

## Vantagens Desse Desenho

- custo inicial mais baixo;
- o cliente pode continuar em hospedagem compartilhada;
- a chave privada nao fica exposta no ambiente do cliente;
- o sistema continua validando localmente sem depender da `license_api` online 24/7;
- o painel comercial de licencas continua sob controle da BTA.

## Desvantagens Desse Desenho

- deploy do sistema principal continua limitado pelas regras da hospedagem compartilhada;
- voce perde boa parte do controle operacional que teria numa VPS;
- atualizacao e troubleshooting tendem a ser mais trabalhosos;
- desempenho e concorrencia tendem a ficar mais limitados;
- o ambiente fica menos portavel e menos previsivel.

## Riscos Reais

### Risco 1: suporte Python do provedor e limitado

Algumas hospedagens compartilhadas dizem suportar Python, mas:

- limitam processos;
- reiniciam apps sem aviso;
- limitam tempo de execucao;
- restringem dependencias nativas;
- dificultam logs e debugging.

### Risco 2: banco e arquivos no mesmo ambiente limitado

Se a aplicacao usar SQLite ou gravar muitos arquivos num ambiente compartilhado, a chance de problemas operacionais aumenta.

### Risco 3: falsa sensacao de economia

O valor mensal pode ser menor, mas o custo tecnico e operacional pode crescer por:

- horas extras de deploy;
- debugging mais demorado;
- instabilidade;
- migracao inevitavel futura.

## Como Fazer do Jeito Menos Arriscado

### Opcao A: hospedagem compartilhada para app principal + VPS barata para `license_api`

Essa e a opcao mais realista se voce quiser insistir em compartilhada.

Arquitetura:

- cliente: hospedagem compartilhada com o sistema principal;
- BTA: VPS barata ou ambiente proprio com a `license_api`.

Essa opcao preserva o mais importante:

- chave privada sob controle da BTA;
- painel de licencas fora do ambiente do cliente;
- validacao local no sistema principal.

### Opcao B: hospedagem compartilhada para app principal + emissao offline pela BTA

Se voce quiser economizar ainda mais no inicio, a BTA pode emitir licencas sem publicar a `license_api` como servico web.

Arquitetura:

- cliente: hospedagem compartilhada com o sistema principal;
- BTA: ambiente local controlado para rodar scripts de emissao.

Fluxo:

1. a BTA roda a emissao localmente;
2. gera a chave assinada;
3. envia a chave ao cliente;
4. o cliente ativa no sistema.

Essa opcao funciona, mas e menos profissional operacionalmente do que manter um backoffice central online.

## O Que a BTA Deve Guardar Fora do Cliente

Independentemente do caminho escolhido, estes itens nao devem ficar no mesmo ambiente do cliente:

- chave privada de emissao;
- base de licencas emitidas;
- painel de revogacao;
- token administrativo da `license_api`;
- trilha comercial completa das emissoes.

## Passo a Passo Simulado

### Cenário simulado

- o cliente insiste em hospedagem compartilhada;
- a BTA quer manter o licenciamento seguro;
- a BTA aceita operar a emissao fora do ambiente do cliente.

### Etapa 1: publicar o sistema principal na hospedagem compartilhada

1. publicar apenas o app principal;
2. garantir que a chave publica esteja disponivel no ambiente do sistema;
3. garantir que o sistema consiga salvar o `installation_id` localmente;
4. validar o login administrativo e a tela de licenca.

### Etapa 2: coletar identificadores da instalacao

1. acessar o painel administrativo do sistema principal;
2. copiar o `ID da instalacao`;
3. confirmar o nome da empresa licenciada.

### Etapa 3: emitir a licenca fora da hospedagem compartilhada

1. acessar o painel ou script de emissao da BTA;
2. definir:
   - empresa;
   - tipo de licenca;
   - plano;
   - limites;
   - vigencia;
   - features;
   - `instance_fingerprint`;
3. gerar a chave assinada;
4. registrar o contrato correspondente.

### Etapa 4: ativar no ambiente do cliente

1. enviar a chave ao cliente;
2. colar a chave no sistema principal;
3. validar status, vigencia, limites e modulos liberados.

## Quando Esse Cenário Ainda Faz Sentido

Esse cenário so faz sentido quando:

- voce quer reduzir custo de entrada ao maximo;
- o cliente aceita um ambiente mais simples;
- a carga de uso e pequena;
- a BTA aceita que a hospedagem compartilhada e um passo temporario.

## Quando Deixa de Fazer Sentido

Deixa de fazer sentido quando:

- houver varios usuarios simultaneos com uso continuo;
- o cliente depender muito de relatorios e uploads;
- voce tiver mais de um sistema relevante no mesmo modelo;
- o suporte tecnico passar a consumir horas demais por causa da infraestrutura;
- o produto entrar em fase de crescimento comercial serio.

## Recomendacao Final

Se voce insistir em hospedagem compartilhada, a forma tecnicamente menos errada e:

1. hospedar apenas o app principal no ambiente compartilhado;
2. manter a `license_api` fora dali;
3. fazer validacao local da licenca no sistema principal;
4. usar esse modelo apenas como etapa temporaria de economia.

Nao trate hospedagem compartilhada como destino final dessa arquitetura. Trate como ponte para uma VPS assim que o produto ou a base de clientes justificarem.