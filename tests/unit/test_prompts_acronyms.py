"""A bare acronym ("O que é MDR?") is far, in embedding space, from the help page that explains it
(cosine 0.33 against a 0.40 gate), and the input classifier took it for general trivia. The prompts
now cover both: the query rewrite spells the term out, and the classifier knows these terms are
Getnet topics (REQ-RAG-05, REQ-GR-03)."""

import pytest

from app.core.prompts import load_prompt

pytestmark = pytest.mark.req("REQ-RAG-05")


def test_query_rewrite_expands_acronyms_into_plain_words() -> None:
    prompt = load_prompt("knowledge")
    assert "acronym or technical term" in prompt
    assert "MDR taxa por transação cobrada do lojista Getnet" in prompt


def test_agent_and_grounding_forbid_acronym_expansions_that_no_source_gives() -> None:
    # The corpus never defines MDR's letters; the model used to supply them from memory, and once
    # it supplied a wrong one ("Taxa de Mero Registro").
    assert "Do not spell out or translate an acronym" in load_prompt("knowledge")
    assert "Acronym expansions need a source" in load_prompt("grounding")


def test_grounding_judges_the_reply_and_not_the_wrong_premise_of_the_question() -> None:
    # "A taxa do débito é 0,1%, certo?": the sources say 0,85%-0,99%. A reply that corrects the
    # premise with those figures is grounded; the checker used to say the reply "claims 0,1%".
    prompt = load_prompt("grounding")
    assert "Judge the reply, not the question" in prompt
    assert "not one that corrects it" in prompt
    # The rules must be numbered in order (a swapped 7 and 8 made the file hard to follow).
    positions = [prompt.index(f"\n{n}. ") for n in range(1, 10)]
    assert positions == sorted(positions)


def test_input_guard_treats_payment_terms_as_getnet_topics() -> None:
    prompt = load_prompt("input_guard")
    assert '"O que é MDR?"' in prompt and '"O que é gravame?"' in prompt
    # The off-topic rule that blocks general trivia must still be there.
    assert "general trivia" in prompt and "out_of_scope" in prompt


def test_knowledge_does_not_merge_terms_of_two_similar_products() -> None:
    # Crediário (até 48x, taxa única) and Parcelado Emissor/Lojista (24x/12x) sit side by side in
    # the corpus; replies that blended them were rightly rejected by the grounding check.
    prompt = load_prompt("knowledge")
    assert "A different product with a similar topic is not the product asked about" in prompt
    assert "never merge terms" in prompt


def test_knowledge_confidence_field_tells_the_model_what_the_number_means() -> None:
    # An English weather answer full of figures was self-rated 0.2 in 3 of 8 runs and escalated.
    from app.agents.knowledge import KnowledgeAnswer

    description = KnowledgeAnswer.model_fields["confidence"].description or ""
    assert "0.8-1.0" in description and "at most 0.2 only when" in description
