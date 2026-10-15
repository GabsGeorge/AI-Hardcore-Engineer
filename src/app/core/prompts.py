"""Versioned prompts loaded from /prompts (ADR 0009).

Cada prompt entrega também um ``prompt.version`` como ``sha256[:12]`` do conteúdo. O span de
cada nó anexa esse atributo (REQ-OBS-02) — assim um A/B muda apenas a versão sem renomear
nada; e qualquer regressão aponta direto para o commit que alterou o texto.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


@lru_cache
def prompt_version(name: str) -> str:
    """Impressão digital estável do texto, mesma formatação binária → mesmo hash."""
    text = load_prompt(name).encode("utf-8")
    return hashlib.sha256(text).hexdigest()[:12]
