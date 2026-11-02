# Backlog de hardening — pós-E2E navegador

**Data**: 2026-11-02 ·
**Fonte**: cruzamento de [e2e-api.md](e2e-api.md) (meu teste via curl) +
[e2e-browser.md](e2e-browser.md) (teste real via navegador).

## Resumo executivo

O teste pelo navegador cobriu 1 cenário (sc07 — HITL) mas encontrou **5 achados
críticos** que o smoke e o teste via API não pegaram, porque todos os anteriores
pularam a sessão web real. Dos 9 achados do relatório do navegador, **4 têm a
mesma causa raiz** (Bug 2 — registro web não cria vínculo `users` + `merchants`
para a conta nova). Os outros 5 são bugs independentes de UX.

## Causa raiz em cascata — Bug 2 explica 4 achados

Quando `/v1/auth/register` cria `auth_accounts` sem o vínculo em `merchants`:

```
1. Lojista novo manda mensagem
   → repo.get_or_create_conversation(user.id=acc_...)
   → INSERT INTO conversations (user_id=acc_...)
   → FK violation (conversations.user_id → users.id, e users não tem acc_...)
   → HTTP 500
```

Isso dispara, em cascata, os seguintes achados do browser:

### A — nginx circuit breaker emite 503 (achados 1, 2, 8 do browser)
```nginx
upstream api_upstream {
  server api:8000 max_fails=3 fail_timeout=30s;
}
```
Depois de 3 HTTP 500 em 30s, o nginx marca o upstream caído e **retorna 503**
para QUALQUER request (chat, logout, me) por 30s sem bater no backend. A
sequência medida no browser (chat 503 → chat 200 → chat 503 → chat 200 →
logout 503 → login 200) é exatamente o padrão esperado do `max_fails=3`:
- 3× 500 consecutivos → `fail_timeout` armado
- 30s depois, nginx tenta de novo
- Se o próximo request ainda falhar (porque o bug continua), volta a 503

**Fix**: resolver Bug 2 (abaixo). Ajuste de nginx não resolve o problema de
fundo — o backend tem que parar de 500ar.

### B — `display_name = cliente1988` após reload (achado 6)
Em [src/app/api/auth.py:92](../../src/app/api/auth.py#L92), o `_from_cookie` já
traduz `account.id` (acc_...) para `merchants.user_id` (cliente1988). Depois, em
[src/app/api/auth_endpoints.py:412](../../src/app/api/auth_endpoints.py#L412), o
endpoint `/v1/auth/me` faz:

```python
account = await repo.get_account_by_id(get_pool(), user.id)
if account is None:
    return AccountOut(id=user.id, role=user.role, display_name=user.id)
```

Como `user.id` já virou `cliente1988`, `get_account_by_id("cliente1988")`
retorna None, cai no fallback e devolve `display_name="cliente1988"`.

**Fix**: `CurrentUser` precisa carregar ambos — `account_id` (original) e
`user_id` (traduzido). O `/me` consulta pelo `account_id`.

### C — Histórico aparece vazio ao abrir conversa (achado 4)
Hipótese: idêntico ao B. O lojista agora consulta mensagens com o id traduzido,
mas as mensagens antigas foram gravadas com o id original. Precisa verificar
`src/app/api/conversations.py` e `src/app/db/repo.py` — qual id é usado como
`user_id` no WHERE das mensagens.

**Investigação pendente**.

## Bugs independentes de UX

### D — Handoff invisível no chat (achado 3 do browser)
O SSE entrega o evento `handoff` com ticket_id, mas a interface não mostra NADA
(`response: ""`). O lojista fica sem saber que caiu em HITL até abrir o
Histórico. **Alta severidade** — compromete toda a UX do fluxo HITL.

**Fix**: no cliente SSE da SPA, quando recebe `handoff.status=awaiting_human`,
renderizar uma bolha-sistema com ticket_id, estimativa de resposta e CTA
"Receber notificação por e-mail" ou similar. Olhar [apps/web/src/chat](../../apps/web/src/chat).

### E — Nenhuma indicação de progresso durante streaming (achado 3)
"Pensando…" aparece e some sem feedback do que está acontecendo. O backend
emite `agent_step` por nó do grafo (input_guardrail, summarize, supervisor,
tool_X). Deveria aparecer na UI como breadcrumb/stepper.

**Fix**: UI consome o canal `agent_step` do SSE e renderiza um stepper com os
nós percorridos; mantém últimos N visíveis.

### F — Histórico sem prévia (achado 5)
Todas as conversas mostram "(sem prévia disponível)". Backend retorna
`last_message_preview = ""`. É cascata de C ou um bug separado (a prévia nunca
é populada no insert?).

### G — Navegação quebrada entre conversas (achado 7)
Clicar em "Conversar" muda URL para `/chat` mas mantém mensagens anteriores
visíveis. Causou a Execução A (mensagem enviada por engano na conversa errada).

**Fix**: ao navegar para `/chat` sem id, limpar o estado do chat.

### H — Primeiro login hang de 10s (achado 9)
Login em `/login?next=/chat/<id>` ficou travado por 10s. Possível redirect
loop ou dependência de outro recurso. **Investigar com Network tab aberto**.

### I — Logout retornou 503, sessão pode estar ativa no servidor
É cascata de A. Se o 503 veio do nginx circuit breaker, o backend **não
revogou a sessão** apesar da UI voltar para o login. Depois do fix de A,
precisa confirmar que o logout chega no backend.

## Priorização para 003-hardening

| Prio | Item | Bugs resolvidos | Esforço |
|---|---|---|---|
| P0 | **Fix Bug 2** — register cria `users` + `merchants` em transação | FK 500, nginx 503, display_name, histórico vazio | **M** (2-4h) |
| P0 | **Fix Bug 3** — admin em `/v1/chat` retorna 403, não 500 | elimina mais uma fonte de 500 que arma o circuit breaker | **XS** (15min) |
| P1 | **UI SSE** — mostrar bolha-sistema no evento `handoff` | D | **S** (1h) |
| P1 | **UI SSE** — stepper com agent_step | E | **S** (1h) |
| P1 | **CurrentUser carregar ambos ids** | B (e provavelmente C) | **S** (1h) |
| P2 | **Fix Bug 1** — `.env.example` com `.example.com` | login do seed default | **XS** (5min) |
| P2 | **Navegação entre conversas** | G | **XS** (15min) |
| P2 | **last_message_preview** no insert | F | **S** (30min) |
| P3 | **Login hang** investigar | H | **?** |
| P3 | **Logout: confirmar revogação após fix A** | I | depende de P0 |

**Total P0+P1**: ~5-7h → já resolve 7 dos 9 achados do navegador + os 3 do meu
teste API.

## Achados que o navegador NÃO cobriu (lacunas intencionais)

- RBAC backend `/v1/chat/stream` como admin (confirmei via curl: HTTP 500,
  mesmo Bug 3)
- 9 cenários do enunciado (sc01-sc06, sc08-sc10) — meu teste API cobriu
- Prompt injection, IDOR, conversa alheia — meu teste API cobriu (3/3 ok)
- Design/UI quality — não foi feito; prompt existe em [docs/reports/ui-review.md](ui-review.md) (se o navegador voltar)

## Credenciais trocadas

A senha `GetnetDemo2026!` foi exposta no transcript da sessão do navegador.
Trocar o `.env` do ambiente real antes de qualquer uso compartilhado.
