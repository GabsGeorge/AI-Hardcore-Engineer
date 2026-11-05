# Regressão do batch 6

**Data:** 2026-11-02 (horário do navegador)
**Ambiente:** `http://localhost/`, viewport de 1484×889
**Conta:** `lojista.qa@getnet.example.com`
**Status:** interrompido. O backend parou de responder durante o teste.

## Resumo

| Teste | Resultado | `trace_id` |
|---|---|---|
| Pré-check | OK | N/A |
| 1. Guardrail aceita bullets | FAIL (knowledge erro) | `e26b15353d7c753e46c665a9e228df09` |
| 2. Composer após resposta longa | Não validado | `7971b265b17b3f44d560581aee9b4e54` |
| 3. Composer bloqueado em handoff | 3/4 OK, falta cinza | `4430404bb9e0e060e877491b649c8f7b` |

**Score: 3/10.** O guardrail deixou a pergunta passar (uma vitória), o bloqueio do composer existe nos 3 criterios funcionais, mas a instabilidade do backend e os erros silenciosos pesam mais.

## Bloqueio de composer (parcial OK)

| Critério | Resultado |
|---|---|
| Campo disabled | OK |
| Placeholder "Aguardando atendente responder..." | OK |
| Linha de aviso | OK |
| Campo com aparência cinza | FAIL |

## Regressões novas

| P | Item | Evidência |
|---|---|---|
| **P0** | Backend instável: /v1/auth/me retornou 500 | Fim da sessao |
| **P0** | HTTP 500 no chat some sem aviso | `a9657fd289d0385393cca1ed8ca4895a` |
| **P1** | Clicar "Conversar" após handoff não abre nova conversa | — |
| **P1** | 500 em /v1/auth/me manda pra /login (parece perda de sessao) | — |
| **P1** | Suporte: "não tenho acesso" apesar de diagnose_terminal ok 2x | `27250057ffa6d4bd6dd6fb0a97dce279` |
| **P2** | Campo bloqueado continua com aparência de ativo | Teste 3 |

search_knowledge_base ainda P0 persistente, agora com status `error` e `timeout`.
