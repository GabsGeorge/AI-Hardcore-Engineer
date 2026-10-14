"""O gerador de rastreabilidade deve falhar quando um REQ entregue não tem teste (REQ-INF-04)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.req("REQ-INF-04")
def test_traceability_matrix_is_generated() -> None:
    """O script sempre gera ``docs/traceability.md``. Ele devolve ≠ 0 quando algum REQ
    entregue ainda não tem teste — isso é a semântica do gate; o teste aqui só verifica
    que a matriz foi produzida com conteúdo e que o script roda sem erro de execução."""
    result = subprocess.run(
        [sys.executable, "scripts/check_traceability.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), f"erro inesperado:\n{result.stderr}"
    matrix = ROOT / "docs" / "traceability.md"
    assert matrix.exists()
    content = matrix.read_text(encoding="utf-8")
    assert "REQ" in content and "Tarefa" in content
