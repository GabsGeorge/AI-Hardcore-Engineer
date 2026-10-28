# UI web — demos por história

Diretório reservado para GIFs curtos (≤ 15 s cada) ilustrando cada história entregue
na spec [002-web-ui](../../specs/002-web-ui/). As gravações são produzidas localmente
via Playwright (ver `apps/web/e2e/visual.spec.ts`) em viewports **desktop** (1280×800)
e **mobile** (390×844).

| História | Arquivo esperado         |
| -------- | ------------------------ |
| US1      | `us1-cadastro-login.gif` |
| US2      | `us2-chat-sse.gif`       |
| US3      | `us3-handoff.gif`        |
| US4      | `us4-historico.gif`      |
| US5      | `us5-privacidade.gif`    |
| US6      | `us6-admin.gif`          |

As gravações são geradas sob demanda (não entram no CI) e não contêm PII — todos os
e-mails/CPFs usam domínio `.example` ou dígitos inválidos.
