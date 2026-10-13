<!--
Sync Impact Report
- Version change: 1.0.0 → 1.0.1 (PATCH: clarification only)
- Previous: template (unversioned) → 1.0.0 (initial ratification)
- Modified: "Fluxo de Desenvolvimento" › Rastreabilidade — commit format clarified to
  `feat(T049): descrição [REQ-...]`, matching task IDs in tasks.md (analyze finding T1)
- Modified principles: none (no principle text changed)
- Added principles: I–XIII (I–XI from the user's constitution prompt;
  XII Simplicidade/Ponytail and XIII Excelência de interface/Impeccable added by the user)
- Added sections: Restrições de Stack e Segurança; Fluxo de Desenvolvimento e Quality Gates
- Removed sections: none
- Templates requiring updates: none (plan/spec/tasks templates read this file at runtime)
- Follow-up TODOs: none
-->

# Getnet Multi-Agent Support System Constitution

## Core Principles

Todos os princípios abaixo são inegociáveis: qualquer mudança que viole um deles é rejeitada,
inclusive por gate automático na CI.

### I. Identidade só do servidor

- O `user_id` efetivo MUST vir exclusivamente do token JWT validado pela API.
- Quando o `user_id` do payload divergir do token, a requisição MUST ser recusada (403) e
  auditada, sem executar nenhum agente ou tool.
- O LLM MUST NOT ver, receber como parâmetro nem escolher identidade. Tools recebem o usuário
  por contexto injetado pelo servidor (`config["configurable"]`), nunca pelo schema da tool.

Racional: aceitar o `user_id` do corpo como identidade abre IDOR (um cliente lê dados de outro).

### II. Nenhum segredo no repositório ou no artefato

- Apenas `.env.example`, sem valores reais, é versionado.
- gitleaks MUST bloquear commit (pre-commit) e build (CI).
- Segredos entram somente por variável de ambiente lida via `pydantic-settings`.

Racional: um único segredo vazado compromete o ambiente e invalida o restante da entrega.

### III. Toda resposta factual tem fonte

- Respostas sobre produtos, tarifas, prazos e dados externos MUST citar as fontes usadas
  (`sources`).
- Sem fonte acima do limiar de relevância, o sistema MUST declarar que não sabe, usar web search
  ou escalar. Inventar resposta é defeito bloqueante.

### IV. Menor privilégio para agentes

- Cada agente MUST ter uma allowlist explícita de tools; o Knowledge não acessa tools de dados
  do cliente.
- Tools com efeito colateral MUST exigir aprovação humana (`interrupt()`) antes de executar.
- Conteúdo recuperado (RAG e web) MUST ser tratado como dado não confiável, delimitado no prompt
  e nunca obedecido como instrução.

### V. Todo requisito tem teste

- Todo requisito (`REQ-*`) MUST ter ao menos um teste marcado com
  `@pytest.mark.req("REQ-...")`; requisito sem teste na matriz de rastreabilidade não está pronto.
- A CI MUST falhar se algum requisito do escopo entregue ficar sem teste.
- Lógica não trivial (branch, parser, dinheiro, segurança, roteamento) MUST ter teste que falhe
  quando ela quebrar.

### VI. Determinismo nos testes

- Testes de CI MUST rodar com LLM fake roteirizado, embeddings fake e sem rede externa.
- LLM real MUST ser usado somente no job de avaliação (golden set, faithfulness, retrieval).

### VII. Observável por padrão

- Toda execução MUST gerar `trace_id` (devolvido na resposta), span por guardrail, agente, tool,
  retrieval e chamada de LLM, e log JSON estruturado.
- PII MUST ser mascarada antes de qualquer sink (log, trace, métrica).

### VIII. Falha segura

- Toda chamada externa MUST ter timeout e retry com backoff; dependências externas MUST ter
  circuit breaker.
- A execução do grafo MUST respeitar `max_steps` e orçamento de tokens.
- Timeout, erro de tool ou orçamento estourado MUST levar a resposta degradada honesta ou a
  escalonamento humano, nunca a resposta inventada nem a loop.

### IX. Reprodutível com um comando

- `docker compose up` MUST subir toda a aplicação (api, banco, redis, ingestão e seed) a partir de
  um clone limpo com apenas `.env` preenchido, sem passos manuais.
- `make test` MUST rodar a suíte inteira dentro do container, sem rede externa.
- A stack de observabilidade (Langfuse, Prometheus, Grafana) sobe com
  `docker compose --profile obs up`, para manter a subida padrão leve na máquina do avaliador.

### X. LGPD e privacidade

- PII (CPF, CNPJ, cartão validado por Luhn, e-mail, telefone) MUST ser mascarada antes do LLM e
  dos logs.
- Histórico e checkpoints MUST ser isolados por usuário.
- A retenção MUST ter prazo padrão definido (configurável por ambiente e documentado no README),
  com expurgo automático dos dados vencidos.
- O sistema MUST oferecer endpoint de exclusão de dados do usuário (`DELETE /v1/me/data`), que
  remove conversas e checkpoints.

### XI. Repositório sem artefatos gerados

- Bancos, índices vetoriais, caches, modelos baixados, `.env` e saídas de build MUST NOT ser
  versionados nem copiados para a imagem; `.gitignore` e `.dockerignore` MUST cobri-los.
- A CI MUST falhar se algum artefato gerado estiver rastreado no repositório.
- Índices e dados mock MUST ser recriados por comando (ingestão e seed), nunca distribuídos.

Racional: artefatos gerados no repositório tornam a entrega não reprodutível e podem carregar dados.

### XII. Simplicidade (Ponytail)

- Todo código de backend MUST ser a menor mudança que resolve o requisito por completo: reutilizar
  o que existe, stdlib e dependências já instaladas antes de código novo.
- Abstrações, wrappers, opções e configuração sem requisito que as peça MUST NOT ser criados.
- Atalhos com limite conhecido MUST ser marcados com `shortcut: <limite>, <quando evoluir>`.
- Simplicidade MUST NOT cortar validação em fronteira de confiança, tratamento de erro que evita
  perda de dados, segurança ou acessibilidade.
- Complexidade adicional MUST ser justificada na tabela "Complexity Tracking" do plano.

### XIII. Excelência de interface (Impeccable)

- Todo trabalho de frontend MUST seguir a skill Impeccable: direção visual definida antes do
  código, design system com tokens documentado em `DESIGN.md`, e revisão final (`audit`/`polish`).
- A interface MUST atender WCAG 2.2 AA, ser responsiva (desktop e mobile) e cobrir estados de
  carregamento, vazio, erro e escalonamento humano.
- Fluxos críticos da interface (chat, handoff e resposta do operador) MUST ter testes E2E com
  Playwright.

## Restrições de Stack e Segurança

- **Linguagem e API:** Python 3.12, FastAPI, Pydantic v2, dependências gerenciadas com `uv` e
  lockfile versionado.
- **Orquestração:** LangGraph (Supervisor em ciclo, `Send`, `Command`, `interrupt`) sobre
  LangChain; estado do grafo tipado e persistido por `thread_id`.
- **LLM:** OpenAI, com modelo principal e modelo de fallback configuráveis por ambiente.
- **Web search:** DuckDuckGo, sempre com cache, timeout e circuit breaker.
- **Persistência:** Postgres com pgvector para vetores, checkpoints, tickets, auditoria e dados
  mock; Redis para rate limit, idempotência e cache.
- **Idioma:** o sistema MUST responder no idioma da mensagem do usuário.
- **Container:** imagem multi-stage, sem root, versões fixadas, healthcheck e scan Trivy sem
  vulnerabilidade crítica.
- **Ameaças:** o design MUST cobrir o OWASP Top 10 for LLM Applications, com mitigação e teste
  por risco registrados no threat model.
- **Dados de cliente:** apenas dados mock com seed determinístico; nenhum dado real de cliente.

## Fluxo de Desenvolvimento e Quality Gates

- **Spec Driven Development:** toda funcionalidade passa por specify → clarify → plan → tasks →
  analyze antes de implement. Código sem task correspondente não entra.
- **Rastreabilidade:** commits referenciam o ID da task como está no `tasks.md` e os requisitos
  (formato `feat(T049): descrição [REQ-SUP-02]`).
- **Escopo por prioridade:** P0 (core) é entregue antes de P1 (diferenciais) e P2 (plataforma);
  o frontend é extensão (P1/P2) e não bloqueia o core. O README MUST distinguir core de extensão.
- **Papéis:** PO (backlog e aceite), especialista em orquestração (grafo e revisão de fluxo),
  backend/agents, frontend/design system, QA e revisor de segurança. Trabalho paralelo MUST usar
  git worktrees isolados.
- **Revisões obrigatórias:** mudanças no grafo MUST ser revisadas pelo especialista em
  orquestração; mudanças em auth, tools, guardrails ou tratamento de PII MUST ser revisadas pelo
  revisor de segurança.
- **Gates de CI:** ruff, mypy, pytest com cobertura ≥ 85% em `src/`, rastreabilidade de
  requisitos, gitleaks, Trivy e build da imagem. Nenhum merge com gate vermelho.

## Governance

- Esta constitution prevalece sobre qualquer outra prática, spec ou plano. Conflitos são
  resolvidos a favor dela ou por emenda explícita.
- Emendas MUST ser feitas via `/speckit-constitution`, com Sync Impact Report, justificativa e
  atualização dos artefatos afetados.
- Versionamento semântico: MAJOR para remoção ou redefinição incompatível de princípio; MINOR
  para princípio ou seção nova ou expandida; PATCH para clarificações.
- Todo plano MUST passar pelo "Constitution Check" antes da pesquisa e novamente após o design;
  toda revisão de código MUST verificar conformidade com os princípios I–XIII.

**Version**: 1.0.1 | **Ratified**: 2026-10-13 | **Last Amended**: 2026-10-13
