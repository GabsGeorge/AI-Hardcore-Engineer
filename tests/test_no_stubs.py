"""Entrega final: nenhum arquivo em ``src/`` pode conter marcadores ``# STUB(``.

Durante a implementação, nós provisórios carregam ``# STUB(T0NN)`` apontando para a tarefa
que os completa (constitution V). Este teste roda na suíte e no CI; qualquer stub remanescente
reprova a entrega, listando arquivo, linha e a tarefa pendente.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_STUB_RE = re.compile(r"#\s*STUB\(([^)]*)\)")
_SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.mark.req("REQ-INF-04")
def test_no_stub_markers_left_in_src() -> None:
    pending: list[str] = []
    for path in _SRC.rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if match := _STUB_RE.search(line):
                rel = path.relative_to(_SRC.parent)
                pending.append(f"{rel}:{i} → STUB({match.group(1)})")
    assert not pending, "STUB markers still present:\n  " + "\n  ".join(pending)
