"""Routing examples the supervisor depends on. Two of them pull in opposite directions and both
must stay: asking what an error code MEANS is a help-center question (knowledge), while reporting
that the merchant's OWN machine shows an error needs the terminal's status (support). Collapsing
them sent "minha maquininha está mostrando erro E12" to knowledge and broke golden sc-04."""

import pytest

from app.core.prompts import load_prompt

pytestmark = pytest.mark.req("REQ-ORC-01")


def test_code_definitions_go_to_knowledge_and_own_machine_errors_to_support() -> None:
    prompt = load_prompt("supervisor")
    assert '"O que significa o erro ADQ 4-91?" → **knowledge**' in prompt
    assert '"Minha maquininha está mostrando erro E12." → **support**' in prompt
    assert "a question about what a code means is `knowledge`" in prompt


def test_decline_code_example_still_routes_to_support() -> None:
    assert '"O que significa o código de recusa 51?" → **support**' in load_prompt("supervisor")


def test_language_is_the_language_of_the_sentence_not_of_the_topic() -> None:
    # The planner called English questions about Brazilian topics "pt", so the whole answer
    # came back in Portuguese (smoke scenarios 02, 03, 06, 07, 09 in English).
    prompt = load_prompt("supervisor")
    assert "WRITTEN in" in prompt
    assert '"How does receivables advance work?" → `en`' in prompt


def test_settle_language_overrules_the_planner_only_when_the_words_agree() -> None:
    from app.graph.synthesize import settle_language

    for en in (
        "How do installments work in crediário?",
        "Euro exchange rate today",
        "How does receivables advance work?",
        "When will yesterday's sales money arrive?",
        "What is the weather forecast for Porto Alegre tomorrow?",
    ):
        assert settle_language(en, "pt") == "en", en
    for pt in ("Como funcionam as parcelas no crediário?", "Cotação do euro hoje"):
        assert settle_language(pt, "en") == "pt", pt
    assert settle_language("Pix", "en") == "en"  # no cue either way: the planner decides


def test_subtask_queries_stay_in_the_merchants_language() -> None:
    # Specialists answer in the language of the query they are handed; a Portuguese query for an
    # English question produced Portuguese answers (smoke 03/en, 07/en).
    assert "Write each `query` in the language of the merchant's message" in load_prompt(
        "supervisor"
    )
