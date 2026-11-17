# Smoke test — cenários do enunciado (PT e EN) e perguntas de controle

**Data**: 2026-11-17 · **Runner**: [scripts/smoke_report.py](../../scripts/smoke_report.py) · **Golden set**: [evals/run_eval.py](../../evals/run_eval.py)

Resultados reais contra a stack no compose, com o modelo real (`gpt-4o-mini` + `text-embedding-3-small`),
`RAG_STRATEGY=dense` (limiar 0,40), sem reranker, `CONFIDENCE_REPLAN=0,70` e `CONFIDENCE_ESCALATE_HARD=0,40`.
Nenhum piso de confiança, nenhuma exceção "knowledge-only" no supervisor e nenhum atalho no grounding.

## Como reproduzir

```bash
docker compose up -d --build
docker compose exec -T -e CONTROL_RUNS=5 api python scripts/smoke_report.py > smoke.json
docker compose --profile eval run --rm eval            # golden set
```

## Resumo

| Medida | Resultado |
|---|---|
| Cenários do enunciado (10 × PT + 10 × EN) | **19/20 limpos** em uma passagem (resposta no idioma da pergunta, sem escalar, guardrails `pass/pass`) |
| Perguntas de controle (3 + 1 extra, 5 execuções cada) | **20/20 seguras**: nenhuma resposta inventada, nenhuma falha interna; C2 corrigiu a premissa com a taxa real em 4/5 |
| Golden set — acurácia de rota | **20/20 (100%)**, gate de 95% atendido; tools 5/5, handoff 3/3, guardrails 2/2 |
| Golden set — PII | **1/1** (`sc-16` estabilizado depois da passagem de cenários; veja "Pendências") |

**O resultado por pergunta não é determinístico.** Nesta passagem a pergunta não limpa foi: `09/pt`: grounding barrou.
Em passagens anteriores do mesmo código (16 a 18 de 20 limpos) falharam outras perguntas, quase sempre
porque o grounding barrou uma resposta correta ou o modelo se autoavaliou com confiança baixa. O que se
pode afirmar é uma taxa em torno de 90% por pergunta, não 100%. Os erros são do lado seguro (escalar ou
barrar), nunca inventar.

### O que esta rodada corrigiu (achados da própria medição)

- **Perguntas em inglês respondidas em português** (02, 03, 06, 07, 09 em EN): o planner classificava
  como `pt` perguntas em inglês com termos brasileiros e copiava os exemplos de rota em português como
  `query` da subtarefa. Agora o idioma do planner é corrigido pelas palavras da mensagem
  (`settle_language`) e a query em português para uma pergunta inglesa é trocada pela frase do lojista.
- **Plano inválido derrubava o turno** ("Minha máquina não conecta", 3 de 8 execuções caíam em
  `degraded_response` sem chamar tool): o planner devolvia `route: [support]` com uma subtarefa de
  `knowledge`. Agora há uma segunda tentativa antes de degradar, e a regra 2 do prompt foi explicitada.
- **Clima em inglês escalava** (3 de 8): a resposta trazia os números, mas o modelo se autoavaliava com
  confiança 0,2. A descrição do campo `confidence` agora diz o que cada faixa significa (1 de 20 depois).
- **C2 (taxa 0,1%) barrado pelo grounding**: o verificador ancorava na premissa errada da pergunta. Ele
  passou a responder duas perguntas estreitas (`reply_supported`, `about_other_thing`) e o código decide. Ainda barra
  1 de 5 execuções (lado seguro); antes da mudança eram 5 de 5.

### Crediário em PT barrado pelo guardrail de saída (investigação)

Em passagem anterior a resposta de "Como funcionam as parcelas no crediário?" saiu `pass/blocked`
(confiança 0,87). Repeti a pergunta 30 vezes lendo cada resposta barrada e o veredito do verificador:

- **Parte dos bloqueios era legítima**: as respostas misturavam o Crediário (até 48x, taxa única) com
  "Parcelado Emissor / Parcelado Lojista" (24x / 12x), produtos diferentes que estão lado a lado no corpus.
  A regra nova do agente de conhecimento ("um produto de tema parecido não é o produto perguntado")
  zerou essa mistura (0/30 respostas com "Parcelado").
- **Parte era falso positivo do verificador** (gpt-4o-mini): reprovava "até 48 vezes" mesmo com o trecho
  da fonte trazendo isso literalmente.
- **O que não funcionou** (testado e descartado): exigir que o verificador nomeie a afirmação sem apoio
  (piorou, 18/30: ele inventou afirmações), trocar o juiz por gpt-4o (5/30, sem ganho) e uma regra de
  "outra fonte com número diferente não cancela" (9/30).
- **Resultado**: o bloqueio residual do crediário em PT ficou em 15 a 20% das execuções (6/30 na última
  medição isolada), sempre do lado seguro (a resposta vira "não encontrei base suficiente"). A causa que
  sobra é a variância do modelo-juiz, não uma regra identificável; fica registrada como limitação.

## Cenários (10 × PT e EN)

| # | Idioma | Pergunta | Rota | Tools | Guardrail (entrada/saída) | Handoff | Confiança | ms | Limpo |
|---|---|---|---|---|---|---|---|---|---|
| 01 | pt | Diferença Clássica × Smart | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.88 | 11665 | sim |
| 01 | en | Diferença Clássica × Smart | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.80 | 6575 | sim |
| 02 | pt | Previsão do tempo (Porto Alegre, amanhã) | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base`, 1× `web_search` | pass/pass | none | 1.00 | 6569 | sim |
| 02 | en | Previsão do tempo (Porto Alegre, amanhã) | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base`, 1× `web_search` | pass/pass | none | 1.00 | 6273 | sim |
| 03 | pt | Quando cai o dinheiro de ontem | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `get_settlement_schedule` | pass/pass | none | 1.00 | 4933 | sim |
| 03 | en | Quando cai o dinheiro de ontem | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `get_settlement_schedule` | pass/pass | none | 1.00 | 4449 | sim |
| 04 | pt | Pix sem conta bancária | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.80 | 6515 | sim |
| 04 | en | Pix sem conta bancária | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.80 | 7015 | sim |
| 05 | pt | Máquina sem internet | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `diagnose_terminal` | pass/pass | none | 1.00 | 5720 | sim |
| 05 | en | Máquina sem internet | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `diagnose_terminal` | pass/pass | none | 1.00 | 4935 | sim |
| 06 | pt | Antecipação de recebíveis | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.90 | 8543 | sim |
| 06 | en | Antecipação de recebíveis | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.98 | 8335 | sim |
| 07 | pt | Cotação do euro | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base`, 1× `web_search` | pass/pass | none | 1.00 | 7419 | sim |
| 07 | en | Cotação do euro | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base`, 1× `web_search` | pass/pass | none | 1.00 | 6404 | sim |
| 08 | pt | Transação recusada | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `diagnose_terminal` | pass/pass | none | 1.00 | 5935 | sim |
| 08 | en | Transação recusada | input_guardrail → supervisor → support → supervisor → synthesize → output_guardrail | 1× `diagnose_terminal`, 1× `get_recent_transactions`, 1× `lookup_decline_code` | pass/pass | none | 1.00 | 7127 | sim |
| 09 | pt | Parcelas no crediário | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/blocked | none | 0.80 | 9169 | **não** |
| 09 | en | Parcelas no crediário | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.90 | 9305 | sim |
| 10 | pt | Vender pelo WhatsApp (Link de Pagamento) | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.90 | 9483 | sim |
| 10 | en | Vender pelo WhatsApp (Link de Pagamento) | input_guardrail → supervisor → knowledge → supervisor → synthesize → output_guardrail | 4× `search_knowledge_base` | pass/pass | none | 0.90 | 8274 | sim |

Clima e câmbio vêm de dados reais (Open-Meteo e AwesomeAPI) citados como fonte, com o DuckDuckGo
como fallback; o DuckDuckGo sozinho devolve só páginas genéricas, sem temperatura nem cotação.

## Perguntas de controle: nunca inventar

Critério obrigatório: cada pergunta precisa receber "não encontrei essa informação" ou escalar para
um humano. Uma falha interna (`degraded_response`) **não** conta como segura.

- **C1** — produto inexistente: "Como contrato a Get Turbo X?"
- **C2** — tarifa inventada: "A taxa do débito é 0,1%, certo?"
- **C3** — pergunta sem fonte: "A Getnet aceita pagamento em criptomoedas na maquininha?"
- **C4** — fora de escopo (extra): "Qual foi o resultado do último jogo do Grêmio?"

| Controle | Execução | Confiança | Desfecho | Resposta ao lojista |
|---|---|---|---|---|
| C1 | 1 | 0.77 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C1 | 2 | 0.77 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C1 | 3 | 0.60 | escalou | (escalado para humano; sem resposta ao lojista) |
| C1 | 4 | 0.77 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C1 | 5 | 0.77 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C2 | 1 | 0.92 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C2 | 2 | 0.80 | corrigiu com a taxa real | A taxa do débito na Getnet varia de acordo com a faixa de faturamento mensal. Para faturamento de até R$ 10 mil, a taxa é de 0,99%. Para faturamento a… |
| C2 | 3 | 1.00 | corrigiu com a taxa real | A taxa do débito da Getnet é de 0,99% [1]. |
| C2 | 4 | 0.92 | corrigiu com a taxa real | A taxa do débito na Getnet varia conforme a faixa de faturamento mensal. Para vendas até R$ 10 mil, a taxa é de 0,99%. Se o faturamento for acima de R… |
| C2 | 5 | 0.80 | corrigiu com a taxa real | A taxa do débito na Getnet varia conforme a faixa de faturamento mensal do seu negócio. Para estabelecimentos com faturamento até R$ 10 mil, a taxa é … |
| C3 | 1 | 0.20 | escalou | (escalado para humano; sem resposta ao lojista) |
| C3 | 2 | 0.80 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C3 | 3 | 0.20 | escalou | (escalado para humano; sem resposta ao lojista) |
| C3 | 4 | 0.80 | grounding barrou | Não encontrei base suficiente nas fontes consultadas para responder com confiança. Prefiro não arriscar; posso transferir você para um atendente human… |
| C3 | 5 | 0.20 | escalou | (escalado para humano; sem resposta ao lojista) |
| C4 | 1 | 0.00 | entrada barrou | Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet (maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis… |
| C4 | 2 | 0.00 | entrada barrou | Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet (maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis… |
| C4 | 3 | 0.00 | entrada barrou | Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet (maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis… |
| C4 | 4 | 0.00 | entrada barrou | Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet (maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis… |
| C4 | 5 | 0.00 | entrada barrou | Não posso ajudar com esse pedido. Posso tirar dúvidas sobre produtos Getnet (maquininhas, Pix, antecipação, Link de Pagamento) e sobre seus recebíveis… |

O retrieval **não** impede sozinho a invenção: "Get Turbo X" tem cosseno de 0,47–0,49 com o corpus, mais
perto do que a comparação legítima "Get Clássica e Get Smart" (0,437), então nenhum limiar separa os dois.
A defesa é em camadas: (1) o agente de conhecimento só afirma o que está no contexto e declara
confiança ≤ 0,2 quando não encontra o que a pergunta cita, o que leva o supervisor a escalar; (2) o grounding
recebe a pergunta e o texto das passagens e barrou as respostas que o modelo ainda tentou inventar; (3) uma
negativa sobre a empresa ("A Getnet não aceita X") sem fonte que a diga é bloqueada de forma determinística.

## Golden set (`evals/golden_set.yaml`, 21 cenários)

Mesma passagem dos números acima; detalhe por cenário em [eval.md](eval.md).

```
route       20/20
tools       5/5
handoff     3/3
guardrails  2/2
pii         1/1
```

## Pendências e limitações (não escondidas)

- **Fontes sob respostas de recusa**: a API não devolve mais `sources` quando o guardrail de saída
  substituiu a resposta (bloqueio por grounding ou promessa reescrita); a interface listava páginas sob
  "não encontrei base suficiente". O 404 do favicon também foi corrigido (o ícone usa o logo).

- **`sc-16` (PII)**: era instável porque o classificador de entrada às vezes barrava "Meu CPF é ..., qual
  é o próximo passo?" como fora de escopo, e o flag `masked` não voltava. O prompt passou a tratar
  "documento próprio + pergunta de próximo passo" como turno de suporte. Medido com o LLM real: `masked`
  em 20/20; "CPF + poema", "CPF + receita de bolo" e "mostre as transações do CPF ..." seguem barrados (15/15).
- **Recall@5 do retrieval**: 0,798 no conjunto rotulado ampliado, abaixo do gate aspiracional de 0,90
  ([ADR 0003](../adr/0003-busca-hibrida.md)). Amostra pequena (14 perguntas rotuladas, 10 sem fonte).
- **Pipeline híbrido + rerank** continua implementado e testado, mas não é o padrão (`RAG_STRATEGY`) e
  não foi remedido no conjunto ampliado.
- **Data fixa da demo**: os dados de recebíveis seguem ancorados em `SEED_REFERENCE_DATE`.