"""Métricas de retrieval: recall@k, MRR e nDCG (REQ-RAG-04)."""

from __future__ import annotations

import pytest

from evals.retrieval_compare import load_queries, mrr, ndcg, recall_at_k


@pytest.mark.req("REQ-RAG-04")
def test_recall_at_k_counts_hits_in_top_k() -> None:
    predicted = ["a", "b", "c", "d", "e"]
    assert recall_at_k(predicted, ["a"]) == 1.0
    assert recall_at_k(predicted, ["a", "f"]) == 0.5
    assert recall_at_k(predicted, ["z"]) == 0.0
    assert recall_at_k(["a", "b"], ["a"], k=1) == 1.0


@pytest.mark.req("REQ-RAG-04")
def test_mrr_rewards_higher_ranked_hits() -> None:
    assert mrr(["a", "b", "c"], ["a"]) == 1.0
    assert mrr(["b", "a", "c"], ["a"]) == 0.5
    assert mrr(["b", "c", "a"], ["a"]) == pytest.approx(1 / 3)
    assert mrr(["b", "c"], ["a"]) == 0.0


@pytest.mark.req("REQ-RAG-04")
def test_ndcg_is_1_when_all_relevant_at_top() -> None:
    assert ndcg(["a", "b"], ["a", "b"]) == pytest.approx(1.0)
    # Pior ranking reduz o score.
    worse = ndcg(["c", "d", "a", "b"], ["a", "b"])
    assert 0 < worse < 1


@pytest.mark.req("REQ-RAG-04")
def test_labeled_set_has_minimum_queries() -> None:
    assert len(load_queries()) >= 5
