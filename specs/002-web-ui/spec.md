# Feature Specification: Interface web do atendimento Getnet

**Feature Branch**: `002-web-ui`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Criar uma UI com login e senha e todas as telas para o projeto usando
impeccable, com a identidade visual da Getnet (https://site.getnet.com.br/ofertas/, o mesmo site
usado no RAG). Contas por autocadastro; perfis lojista, operador e admin; React + Vite + TS."

Esta feature dá rosto à plataforma da feature 001: hoje o atendimento só existe como API e os
tokens de acesso saem de um script. Ela cria contas com senha, as telas de cada perfil e a camada
de sessão que a API ainda não tem, sem mudar a regra de identidade da 001 (o usuário efetivo vem
sempre do token emitido pelo servidor).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lojista cria a conta e entra (Priority: P1)

Um lojista que nunca usou a plataforma se cadastra com nome, e-mail e senha, confirma o e-mail
pelo link recebido e entra. Se esquecer a senha, pede um link de redefinição. Ao terminar, sai
da conta, e o aparelho não guarda acesso.

**Why this priority**: sem conta não existe nenhuma outra tela; é a porta de entrada e a
fronteira de segurança da interface.

**Independent Test**: cadastrar um e-mail novo, abrir o link de confirmação na caixa de entrada
de desenvolvimento, entrar, sair e confirmar que a área logada não abre mais sem novo login.

**Acceptance Scenarios**:

1. **Given** um e-mail ainda não usado, **When** o visitante se cadastra com senha válida,
   **Then** a conta nasce como lojista não verificado e um link de confirmação é enviado.
2. **Given** uma conta não verificada, **When** a pessoa tenta entrar, **Then** o acesso é
   negado com orientação para confirmar o e-mail e opção de reenviar o link.
3. **Given** o link de confirmação válido, **When** é aberto, **Then** a conta fica verificada e
   a pessoa pode entrar.
4. **Given** um e-mail já cadastrado, **When** alguém tenta se cadastrar com ele, **Then** a
   tela mostra a mesma mensagem de um cadastro novo ("se o e-mail for válido, enviamos um link"),
   sem revelar que a conta existe.
5. **Given** cinco senhas erradas seguidas para a mesma conta, **When** chega a sexta
   tentativa, **Then** a conta fica bloqueada temporariamente e a tela informa quando tentar de
   novo, sem dizer se o e-mail existe.
6. **Given** um pedido de redefinição de senha, **When** o link é usado dentro do prazo, **Then**
   a senha muda, todas as sessões anteriores da conta deixam de valer e o link não serve de novo.
7. **Given** uma sessão ativa, **When** a pessoa clica em sair, **Then** a sessão é encerrada no
   servidor e voltar com o botão "voltar" do navegador não reabre a área logada.

---

### User Story 2 - Lojista conversa com o atendimento (Priority: P1)

O lojista logado digita uma dúvida e vê a resposta sendo construída: em que etapa o atendimento
está, a resposta final, as fontes consultadas e, quando o caso vai para uma pessoa, o status do
chamado e a resposta do atendente quando ela chegar, sem recarregar a página.

**Why this priority**: é o valor central do produto; as demais telas existem para sustentar
esta.

**Independent Test**: com uma conta lojista, perguntar "Como funciona a antecipação?" e ver
etapas, resposta com fontes clicáveis; pedir "quero falar com um humano", responder pela tela do
operador e ver a resposta chegar sozinha na conversa do lojista.

**Acceptance Scenarios**:

1. **Given** uma conversa aberta, **When** o lojista envia uma pergunta, **Then** a tela mostra
   as etapas em andamento e, ao final, a resposta com as fontes (título e link) e a data de
   consulta das fontes da web.
2. **Given** uma pergunta que vira chamado humano, **When** o atendimento responde, **Then** a
   conversa mostra "aguardando atendente" com o número do chamado.
3. **Given** um chamado aberto que passou do prazo de atendimento, **When** o prazo estoura,
   **Then** a conversa avisa o lojista que o atendimento está demorando mais que o previsto.
4. **Given** um chamado aberto, **When** o operador responde, **Then** a resposta aparece na
   conversa do lojista em até 5 segundos, sem recarregar a página.
5. **Given** um chamado expirado, **When** o prazo final passa, **Then** a conversa mostra a
   mensagem de encerramento e permite começar de novo.
6. **Given** uma mensagem bloqueada pelo guardrail (fora de escopo ou tentativa de injeção),
   **When** a resposta chega, **Then** a tela mostra a recusa educada com os temas atendidos.
7. **Given** qualquer resposta, **When** ela contém texto vindo do modelo ou de fontes,
   **Then** a tela exibe esse texto como texto, sem interpretar marcação nem executar conteúdo.
8. **Given** o lojista escreve em inglês, **When** a resposta chega, **Then** ela está em inglês
   e a interface acompanha o idioma escolhido pelo usuário.

---

### User Story 3 - Operador atende a fila de chamados (Priority: P1)

O operador entra, vê a fila de chamados aguardando atendimento ordenada por prioridade e prazo,
abre um chamado com o resumo e o contexto do caso, responde e, quando há uma ação sensível
pendente (por exemplo, abrir contestação), aprova ou rejeita.

**Why this priority**: sem a tela do operador o fluxo humano da 001 não fecha pela interface; é
o par obrigatório da história 2.

**Independent Test**: com um chamado aberto por um lojista, entrar como operador, ver o chamado
no topo da fila, responder e confirmar que ele sai da fila e que o lojista recebe a resposta.

**Acceptance Scenarios**:

1. **Given** chamados abertos, **When** o operador abre a fila, **Then** vê os chamados com
   prioridade, motivo, tempo restante de prazo e resumo, os de prioridade alta primeiro.
2. **Given** um chamado com ação pendente, **When** o operador tenta responder sem decidir,
   **Then** a tela exige aprovar ou rejeitar antes de enviar.
3. **Given** dois operadores no mesmo chamado, **When** o segundo envia depois do primeiro,
   **Then** vê que o chamado já foi encerrado e a fila se atualiza.
4. **Given** um lojista logado, **When** tenta abrir qualquer tela de operador, **Then** recebe
   a tela de acesso negado e nenhum dado de chamado é carregado.
5. **Given** a fila aberta, **When** novos chamados chegam, **Then** a fila se atualiza sozinha
   em até 30 segundos.

---

### User Story 4 - Lojista retoma conversas anteriores (Priority: P2)

O lojista vê a lista das próprias conversas, da mais recente para a mais antiga, com o status do
chamado de cada uma, e abre qualquer uma para continuar de onde parou.

**Why this priority**: a memória da conversa já existe na 001; sem lista, o lojista perde o
acesso a ela ao fechar a aba.

**Independent Test**: criar duas conversas, sair, entrar de novo e reabrir a primeira com o
histórico completo.

**Acceptance Scenarios**:

1. **Given** conversas anteriores, **When** o lojista abre o histórico, **Then** vê só as
   próprias conversas, com data da última atividade e status do chamado.
2. **Given** o endereço de uma conversa de outra pessoa, **When** o lojista o abre, **Then** a
   tela mostra "conversa não encontrada", igual a uma conversa inexistente.

---

### User Story 5 - Lojista cuida da própria privacidade e avalia o atendimento (Priority: P2)

O lojista avalia cada resposta com positivo ou negativo e um comentário opcional, e pode excluir
todos os seus dados de conversa, entendendo antes o que será apagado.

**Why this priority**: a exclusão é obrigação da LGPD (princípio X) e a avaliação alimenta a
melhoria contínua; ambas já existem na API sem tela.

**Independent Test**: avaliar uma resposta; excluir os dados e confirmar que o histórico ficou
vazio e que a sessão continua válida.

**Acceptance Scenarios**:

1. **Given** uma resposta, **When** o lojista avalia, **Then** a avaliação é registrada e o
   botão mostra o estado escolhido.
2. **Given** o pedido de exclusão, **When** o lojista confirma digitando a palavra pedida,
   **Then** as conversas somem do histórico e a tela informa o que foi apagado e o que foi
   mantido anonimizado.

---

### User Story 6 - Admin gerencia contas e acompanha a operação (Priority: P2)

O admin cria contas de operador e de outros admins (que nunca se autocadastram), vincula a conta
de um lojista ao estabelecimento correspondente, desativa contas e acompanha a operação: tamanho
da fila, chamados fora do prazo e os eventos de auditoria recentes.

**Why this priority**: o autocadastro só cria lojistas; sem admin não há como criar operadores
nem ligar um lojista aos seus dados de estabelecimento.

**Independent Test**: como admin, criar um operador, que entra e vê a fila; vincular um lojista
autocadastrado a um estabelecimento e confirmar que o atendimento passa a responder com os dados
desse estabelecimento.

**Acceptance Scenarios**:

1. **Given** o admin logado, **When** cria uma conta de operador, **Then** o operador recebe um
   link para definir a própria senha; o admin nunca vê nem define a senha de outra pessoa.
2. **Given** uma conta desativada, **When** ela tenta usar uma sessão já aberta, **Then** a
   próxima ação é recusada e a pessoa volta para a tela de login.
3. **Given** um lojista sem vínculo, **When** pergunta sobre os próprios recebíveis, **Then** o
   atendimento informa que a conta ainda não está ligada a um estabelecimento.
4. **Given** um operador ou lojista logado, **When** tenta abrir qualquer tela de admin, **Then**
   recebe acesso negado.
5. **Given** a tela de auditoria, **When** o admin a abre, **Then** vê os eventos sem nenhum dado
   pessoal em claro.

---

### Edge Cases

- A sessão expira no meio de uma conversa: a mensagem digitada não se perde e, após entrar de
  novo, a pessoa volta para a mesma conversa.
- A conexão em tempo real cai durante uma resposta: a tela mostra que está reconectando e, ao
  voltar, exibe o estado final da conversa sem duplicar mensagens.
- O limite de mensagens por minuto é atingido: a tela informa quanto tempo esperar e mantém o
  texto digitado.
- O mesmo envio é disparado duas vezes (duplo clique, rede instável): o atendimento roda uma vez
  só.
- Link de confirmação ou de redefinição expirado ou já usado: mensagem clara e opção de pedir
  outro, sem revelar se a conta existe.
- Lojista cola CPF, cartão ou e-mail na mensagem: o histórico salvo mostra o dado mascarado.
- Resposta do modelo contendo HTML, script ou link malicioso: é exibida como texto.
- Conta desativada ou com papel alterado durante a sessão: a próxima ação reflete o novo estado.
- Tela estreita (celular): todas as telas funcionam sem rolagem horizontal.
- Leitor de tela: a chegada de novas mensagens e mudanças de status é anunciada.

## Requirements *(mandatory)*

### Functional Requirements

**Contas e sessão**

- **FR-001**: O sistema MUST permitir autocadastro com nome, e-mail e senha, criando sempre o
  papel lojista; operador e admin MUST NOT ser obtidos por autocadastro.
- **FR-002**: O sistema MUST exigir confirmação de e-mail antes do primeiro acesso, por link de
  uso único que expira em 24 horas, com opção de reenvio.
- **FR-003**: Senhas MUST ter no mínimo 12 caracteres, sem regras de composição, e MUST ser
  recusadas se estiverem numa lista de senhas comuns ou vazadas; MUST ser guardadas apenas como
  hash resistente a força bruta.
- **FR-004**: Mensagens de cadastro, login e redefinição MUST ser iguais para e-mail existente e
  inexistente (sem enumeração de contas).
- **FR-005**: Após 5 falhas de login seguidas na mesma conta, o acesso MUST ficar bloqueado por
  15 minutos; tentativas de login MUST também ser limitadas por origem.
- **FR-006**: O sistema MUST oferecer redefinição de senha por link de uso único que expira em
  1 hora; trocar a senha MUST encerrar todas as sessões da conta.
- **FR-007**: A sessão MUST ser emitida e validada pelo servidor, expirar por inatividade em 30
  minutos e no máximo em 12 horas, e MUST ser revogável (sair, troca de senha, desativação).
- **FR-008**: As credenciais de sessão MUST ficar fora do alcance de scripts da página e MUST
  ser protegidas contra requisições forjadas de outros sites.
- **FR-009**: O usuário efetivo de toda ação MUST continuar vindo apenas da sessão validada pelo
  servidor (princípio I da constituição); a interface MUST NOT enviar identidade própria.

**Chat do lojista**

- **FR-010**: A tela de conversa MUST mostrar em tempo real as etapas do atendimento e a
  resposta final com fontes clicáveis (título, link e, para web, data de consulta).
- **FR-011**: A conversa MUST mostrar o status do chamado humano (aguardando, prazo estourado,
  respondido, expirado) e receber a resposta do atendente sem recarregar a página.
- **FR-012**: Todo texto vindo do modelo, das fontes ou de outros usuários MUST ser exibido como
  texto puro, sem interpretar marcação nem executar conteúdo.
- **FR-013**: A interface MUST impedir envio duplicado de uma mesma mensagem e MUST informar o
  tempo de espera quando o limite por minuto for atingido, preservando o texto digitado.
- **FR-014**: O lojista MUST ver e reabrir apenas as próprias conversas; conversa de terceiro
  MUST ter a mesma resposta de conversa inexistente.
- **FR-015**: O lojista MUST poder avaliar cada resposta (positivo/negativo, comentário opcional
  de até 1000 caracteres).
- **FR-016**: O lojista MUST poder excluir os próprios dados de conversa, com confirmação
  explícita e um resumo do que foi apagado e do que permaneceu anonimizado.

**Operador**

- **FR-017**: A fila MUST listar os chamados aguardando atendimento, prioridade alta primeiro e
  depois por prazo, com motivo, tempo restante e resumo, atualizando-se em até 30 segundos.
- **FR-018**: O detalhe do chamado MUST mostrar resumo, contexto e ação pendente; responder um
  chamado com ação pendente MUST exigir aprovar ou rejeitar.
- **FR-019**: Responder um chamado já encerrado MUST mostrar que ele foi encerrado e atualizar a
  fila, sem duplicar a resposta.

**Admin**

- **FR-020**: O admin MUST poder criar contas de operador e admin; a pessoa criada MUST definir a
  própria senha por link de uso único.
- **FR-021**: O admin MUST poder vincular a conta de um lojista a um estabelecimento existente e
  desvincular; um lojista sem vínculo MUST NOT ter acesso a dados de nenhum estabelecimento.
- **FR-022**: O admin MUST poder desativar e reativar contas; uma conta desativada MUST perder
  as sessões abertas.
- **FR-023**: O admin MUST ver a situação da fila (abertos, fora do prazo, expirados no dia) e
  os eventos de auditoria recentes, sem dados pessoais em claro.

**Acesso e auditoria**

- **FR-024**: Cada tela MUST exigir o papel correspondente; papel errado MUST ver acesso negado
  sem que nenhum dado protegido seja carregado.
- **FR-025**: Cadastro, confirmação, login (sucesso e falha), bloqueio, redefinição, saída,
  criação, vínculo e desativação de conta MUST gerar evento de auditoria sem senha nem e-mail
  em claro.

**Experiência (princípio XIII)**

- **FR-026**: A interface MUST seguir a identidade visual pública da Getnet (paleta, tipografia,
  tom), com as decisões documentadas num design system com tokens.
- **FR-027**: A interface MUST atender WCAG 2.2 AA e funcionar em desktop e celular.
- **FR-028**: Toda tela MUST tratar os estados de carregamento, vazio, erro e, no chat,
  escalonamento humano.
- **FR-029**: A interface MUST estar disponível em português e inglês.
- **FR-030**: Os fluxos de cadastro e login, chat, chamado humano com resposta do operador e
  controle de acesso por papel MUST ter testes ponta a ponta automatizados.

### Key Entities

- **Conta**: pessoa que usa a interface; nome, e-mail (único, guardado de forma a não aparecer em
  logs), hash da senha, papel (lojista, operador, admin), situação (pendente de confirmação,
  ativa, bloqueada até, desativada) e, para lojista, o estabelecimento vinculado (opcional).
- **Sessão**: acesso ativo de uma conta; criada no login, com expiração por inatividade e
  absoluta, revogável individualmente ou em massa.
- **Link de uso único**: confirmação de e-mail, redefinição de senha ou definição da primeira
  senha; ligado a uma conta, com finalidade, validade e marca de uso.
- **Estabelecimento**: os dados de lojista que já existem na 001 (plano, terminais, transações,
  recebíveis); passa a ser ligado a uma conta pelo admin.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um lojista novo vai do cadastro à primeira resposta do atendimento em menos de 3
  minutos, contando a confirmação de e-mail.
- **SC-002**: A primeira etapa do atendimento aparece na tela em até 1 segundo após o envio, e a
  resposta do operador chega à conversa do lojista em até 5 segundos.
- **SC-003**: Um operador abre a fila e responde um chamado em até 4 interações.
- **SC-004**: Zero acessos indevidos nos testes de controle: nenhuma tela ou chamada de um papel
  retorna dados de outro papel ou de outro usuário.
- **SC-005**: Zero violações WCAG 2.2 AA críticas ou sérias na varredura automática de todas as
  telas, em desktop e celular.
- **SC-006**: 100% dos fluxos críticos (FR-030) cobertos por testes ponta a ponta verdes na CI.
- **SC-007**: Nenhuma tela exige rolagem horizontal em larguras a partir de 360 px.

## Assumptions

- **Contas de demonstração**: fora de produção, os usuários já semeados da 001 (`cliente1988`,
  `cliente2024`, `operador01`) ganham e-mail e senha definidos no ambiente, e um admin inicial é
  criado do mesmo jeito; em produção, o primeiro admin é criado por comando, nunca por tela.
- **Vínculo com estabelecimento**: o autocadastro não liga a conta a nenhum dado de
  estabelecimento; só o admin vincula. Ligar por CNPJ informado pelo próprio usuário daria acesso
  aos dados de terceiros e foi descartado.
- **E-mail**: não há provedor de e-mail no projeto; no ambiente local os e-mails vão para uma
  caixa de entrada de desenvolvimento acessível pelo navegador. O envio real fica fora do escopo.
- **Identidade visual**: segue o site público da Getnet (vermelho principal `#EC0000`, textos
  `#282828`, cinzas `#454C52`/`#66707A`/`#E1E6EB`/`#F5F7FA`, cantos de 8 px). A fonte do site
  (Santander/Santander Text) é proprietária e não será embutida; usa-se uma fonte aberta de
  características próximas. O logotipo é o publicado no site, com uso restrito a esta
  demonstração.
- **Idioma**: português é o padrão; inglês é escolhido pelo usuário. O idioma das respostas do
  atendimento continua seguindo a mensagem, como na 001.
- **Navegadores**: as duas últimas versões de Chrome, Edge, Firefox e Safari, desktop e celular.
- **Fora do escopo**: login social, autenticação em dois fatores, envio real de e-mail,
  aplicativo nativo e personalização visual por lojista.
- **Dependências**: reutiliza a API da 001 (chat em streaming, conversas, chamados, feedback,
  exclusão de dados). Ainda não existem e entram nesta feature: contas e sessão, listagem de
  conversas do lojista, sinal de prazo estourado do chamado para o lojista, e as operações de
  admin (contas, vínculo, visão da fila e da auditoria).
