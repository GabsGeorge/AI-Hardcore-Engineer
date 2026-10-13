import pytest
from app.rag.retriever import RRF_K, rrf

pytestmark = pytest.mark.req("REQ-RAG-04")


def test_rrf_uses_k_60_and_sums_reciprocal_ranks() -> None:
    assert RRF_K == 60
    fused = rrf([[1, 2, 3], [3, 1]])
    assert [doc for doc, _ in fused] == [1, 3, 2]
    scores = dict(fused)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[2] == pytest.approx(1 / 62)


def test_rrf_rewards_agreement_between_lists() -> None:
    # 7 is second in both lists and beats items that are first in only one of them.
    fused = rrf([[5, 7, 8], [6, 7, 9]])
    assert fused[0][0] == 7


def test_rrf_of_nothing_is_empty() -> None:
    assert rrf([]) == [] and rrf([[], []]) == []
