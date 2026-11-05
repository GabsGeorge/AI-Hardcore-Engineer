# E2E: cadastro novo e primeiro chat

**Data:** 2026-11-02, cerca de 11:47–11:53 (America/Sao_Paulo)
**Ambiente:** `http://localhost/`, Chrome com a extensão Claude in Chrome, sem ajustes no stream
**Conta:** `lojista.qa@getnet.example.com` (fictícia), ativada manualmente no banco

## Resumo

| Passo | Resultado | Observação |
|---|---|---|
| 1. Cadastro | OK | 202 em 494 ms |
| 2. Login | OK | `/chat`, com `display_name = Lojista Teste QA` |
| 3a. Vendas de ontem | FAIL | Bloqueada pelo guardrail |
| 3b. Antecipação | FAIL | Virou handoff, sem resposta |
| 3c. Terminal offline | FAIL | Virou handoff, sem resposta |
| 4. Histórico | FAIL | Conversa listada, mas sem prévia e sem mensagens |
| 5. Logout e relogin | ALERTA | Sessão e lista OK; o conteúdo continua invisível |

**Score final: 4/10.** Autenticação, sessão e continuidade da conversa funcionam. Porém nenhuma das 3 perguntas teve resposta útil, e o lojista não consegue reler a conversa. O chat renderizar sem ajuste é um avanço real em relação à revisão anterior.

Os status vêm da Resource Timing e do `fetch` no navegador, porque a leitura de rede da extensão já se mostrou incorreta. Os `trace_id` vêm do evento `done`.

## Passo 1: cadastro OK

`POST /v1/auth/register` retornou 202 em 494 ms, e a tela de verificação apareceu.

![Cadastro preenchido](e2e-register-flow-screenshots/01-cadastro-preenchido.jpg)

![Verifique sua caixa de entrada](e2e-register-flow-screenshots/02-verifique-email.jpg)

## Passo 2: login OK

Após a ativação no banco, `POST /v1/auth/login` retornou 200 em 231 ms e redirecionou para `/chat`. O nome se manteve após recarregar a página.

Confirmei `/v1/auth/me` com uma chamada `fetch` na própria página, não no painel DevTools:

```text
200  id=acc_01M6EBM7KQH14GW8X8KMKGECJM  role=merchant  display_name=Lojista Teste QA
```

![Home logada](e2e-register-flow-screenshots/03-home-logada.jpg)

## Passo 3: chat

| Pergunta | HTTP | `trace_id` | Rota | Tools | Duração | Visto |
|---|---|---|---|---|---:|---|
| a | 200 | `af7a077c99b886d3aa28db564e4068c6` | `input_guardrail` → `safe_response` | Nenhuma | 1,7 s | Mensagem de bloqueio |
| b | 200 | `f88685e36dd60761bdfeead2d602cd27` | `input_guardrail` → `supervisor` → `knowledge` → `supervisor` | `search_knowledge_base`: 4 timeouts | 19,9 s | Aviso de fila e bolha vazia |
| c | 200 | `f3ac7afee96e057c54e5271f600bdac8` | `input_guardrail` → `supervisor` → `knowledge` → `support` → `supervisor` | 4 timeouts; `diagnose_terminal` ok | 12,0 s | Bolha vazia |

| Observação | Resultado | Detalhe |
|---|---|---|
| Bolha do usuário imediata | OK | Apareceu logo após o envio |
| Resposta sem recarregar | OK | Bloqueio e handoff renderizaram sem ajuste |
| Streaming do texto | FAIL | Nenhum evento de texto; só `agent_step`, `handoff` e `done` |
| Passos do agente | OK | Pills surgem durante a execução, com nomes técnicos |
| Markdown | Não avaliado | Nenhuma resposta teve formatação |
| Fontes | Não avaliado | `sources` veio vazio nas 3 perguntas |
| Continuidade | OK | As 3 perguntas ficaram na conversa `daeca7bc` |

### 3a FAIL

- **Esperado:** consulta aos dados de vendas.
- **Visto:** "Não posso ajudar com esse pedido", com `guardrails.input = blocked`.

### 3b FAIL

- **Esperado:** explicação da antecipação, idealmente com fontes.
- **Visto:** aviso "Aguardando atendente" com UUID e bolha vazia, com `confidence = 0` e `response` vazio.

### 3c FAIL

- **Esperado:** diagnóstico e próximos passos.
- **Visto:** `diagnose_terminal` retornou ok em 10 ms, mas a conversa foi para handoff e a bolha ficou vazia.

Não sei se a conta sem estabelecimento vinculado influenciou esse resultado. Vale conferir pelo `trace_id`.

## Passo 4: Histórico FAIL

| Item | Status |
|---|---|
| Conversa aparece na lista | OK |
| Prévia da última mensagem | FAIL `last_message_preview` vazio; a tela mostra "(sem prévia disponível)" |
| Abrir conversa e ver 3 perguntas e 3 respostas | FAIL Tela vazia; o clique não fez nenhuma requisição de mensagens |
| Abrir pela URL direta | FAIL Mesmo resultado; só houve `GET /v1/auth/me` |

## Passo 5: logout e relogin ALERTA

- **Logout:** OK `POST /v1/auth/logout` retornou 204, e `/v1/auth/me` passou a retornar 401.
- **Relogin:** OK levou a `/chat` com o nome correto.
- **Persistência:** ALERTA a conversa continua na lista com o status "Aguardando atendente", mas as mensagens seguem invisíveis.

## Bugs novos

| Prioridade | Bug | Evidência |
|---|---|---|
| **P0** | Pergunta de suporte com tool ok termina em handoff sem resposta: o diagnóstico é descartado | 3c, `f3ac7afee96e057c54e5271f600bdac8` |
| **P0** | "Quais foram minhas vendas de ontem?" é bloqueada, embora o próprio guardrail diga atender transações | 3a, `af7a077c99b886d3aa28db564e4068c6` |
| **P1** | Pergunta de terminal é roteada para `knowledge` antes de `support`, somando cerca de 5 s de timeouts | Rota de 3c |
| **P1** | A página não rola até a nova resposta; após 3b, o composer ficou em y=560 com viewport de 529 px | 3b e 3c |
| **P2** | O aviso de fila fica fora de vista no topo enquanto a conversa cresce | Screenshot 08 |

## Bugs já conhecidos que continuam abertos

| Prioridade | Bug |
|---|---|
| **P0** | `search_knowledge_base` expirou em todas as chamadas |
| **P0** | Conversa do Histórico abre vazia |
| **P1** | Prévia do Histórico vazia |
| **P1** | Bolha vazia em handoff, com UUID como número da fila |
| **P2** | Rota com nomes técnicos e sem streaming de texto |

## Corrigido desde a revisão anterior

- O chat renderiza respostas e handoff sem ajuste, embora o servidor ainda use CRLF.
- Mensagens seguintes permanecem na mesma conversa.
- `display_name` se mantém após recarregar.
- O cadastro levou 494 ms e o login 231 ms nesta execução, bem abaixo do observado antes. Foi só uma medição de cada.

## Efeitos no ambiente

Ficaram a conta de teste e a conversa `daeca7bc`, com o ticket `3834f312-baf4-4fb5-a3c6-2edd899b5f4a` em espera. A conta continua com sessão aberta no navegador.
