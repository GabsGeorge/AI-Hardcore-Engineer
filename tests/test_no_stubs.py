"""Entrega final: nenhum arquivo em ``src/`` ou ``apps/web/src/`` pode conter marcadores de stub.

Durante a implementação, nós provisórios carregam ``# STUB(T0NN)`` (Python) ou ``// STUB(T0NN)``
(TSX/TS) apontando para a tarefa que os completa (constitution V). Este teste roda na suíte e
no CI; qualquer stub remanescente reprova a entrega, listando arquivo, linha e a tarefa pendente.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PY_STUB_RE = re.compile(r"^\s*#\s*STUB\(([^)]*)\)")
_TS_STUB_RE = re.compile(r"^\s*//\s*STUB\(([^)]*)\)")
_ROOT = Path(__file__).resolve().parent.parent
_SRC_PY = _ROOT / "src"
_SRC_WEB = _ROOT / "apps" / "web" / "src"


@pytest.mark.req("REQ-INF-04")
def test_no_stub_markers_left_in_src() -> None:
    pending: list[str] = []
    for path in _SRC_PY.rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if match := _PY_STUB_RE.search(line):
                rel = path.relative_to(_ROOT)
                pending.append(f"{rel}:{i} → STUB({match.group(1)})")
    if _SRC_WEB.is_dir():
        for pattern in ("*.ts", "*.tsx"):
            for path in _SRC_WEB.rglob(pattern):
                for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if match := _TS_STUB_RE.search(line):
                        rel = path.relative_to(_ROOT)
                        pending.append(f"{rel}:{i} → STUB({match.group(1)})")
    assert not pending, "STUB markers still present:\n  " + "\n  ".join(pending)
