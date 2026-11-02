# Teste E2E pelo navegador: Atendimento Getnet

**Data:** 2026-11-02, 01:02–01:11 (America/Sao_Paulo)
**Ambiente:** `http://localhost/`, Chrome com a extensão Claude in Chrome
**Contas usadas:** `lojista@getnet.example.com` e `admin@getnet.example.com`
**Status:** parcial

> **Correção de 2026-11-02.** O "503 intermitente" deste relatório foi um erro de medição. A leitura de rede da extensão registrou 503, mas a Resource Timing e o `fetch` no navegador mediram 200 no chat e 204 no logout. Os achados 1, 2 e 8 ficam retirados. O achado 3 tem causa comprovada: o servidor separa eventos SSE com CRLF, e o parser do front espera LF. Detalhes em `ui-review.md`.

## Resumo

| Item | Resultado |
|---|---|
| Login como lojista | Aprovado na 2ª tentativa; a 1ª ficou travada |
| Sc07, handoff no backend | Conversa fica `awaiting_human`; ticket confirmado em 1 envio |
| Sc07, experiência na tela | **Reprovado:** o lojista não vê resposta, status nem erro |
| Estabilidade dos POSTs | Sem problema confirmado; o 503 foi erro de medição |
| GIF do HITL | Gravado, mas mostra a falha, não um fluxo bem-sucedido |
| Outros 9 cenários | Não executados, por decisão do Santos; o `smoke.md` não estava acessível na sessão |
| RBAC (admin em `/chat`) | **Aprovado na interface:** "Acesso negado" após o login e no acesso direto à URL |

## Achados (atualizados)

| # | Severidade | Achado | Evidência |
|---|---|---|---|
| 1 | Retirado | Erro de medição: envios retornaram 200 no navegador. | — |
| 2 | Retirado | Consequência do erro de medição do achado 1. | — |
| 3 | **Alta** | O chat não lê os eventos `handoff` e `done`, porque o stream usa CRLF e o parser espera LF. | Comprovado em `ui-review.md` |
| 4 | Alta | Abrir conversa do Histórico mostra chat vazio; o log só registra `GET /v1/me/conversations`, sem busca de mensagens. | 11 aberturas por clique |
| 5 | Média | Todas as conversas visíveis no Histórico mostram "(sem prévia disponível)". | Tela e API |
| 6 | Média | O nome muda de "Lojista Demo" para `cliente1988` após recarregar. `/v1/auth/me` retorna display_name igual ao id interno. | Tela e API |
| 7 | Média | Ir de uma conversa para "Conversar" muda URL para `/chat`, mas mantém mensagens anteriores. | Causou a execução A |
| 8 | Retirado | Logout retornou 204; `/v1/auth/me` passou a dar 401. | — |
| 9 | A investigar | Login levou mais de 10s. | — |

## Causa raiz do achado 3 — SSE CRLF vs LF

Backend emite eventos SSE separados por `\r\n\r\n`. Parser do front faz `buffer.split("\n\n")`, nunca encontra o separador e nunca emite `done`/`handoff`. Patch comprovado no navegador: `buffer.replace(/\r\n/g, "\n")` antes do split faz a resposta aparecer.

Correção definitiva: no cliente SSE da SPA, usar regex `/\r?\n\r?\n/` ou normalizar o buffer. No backend, não há tanto risco de regressão porque EventSource nativo lida com os dois — o parser customizado da SPA é o problema.

## RBAC

Admin em `/chat` → "Acesso negado" (tela). Backend `POST /v1/chat/stream` como admin **não foi testado pelo navegador** — meu teste via curl confirmou HTTP 500 (Bug conhecido).
