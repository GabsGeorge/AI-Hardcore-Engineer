"""Structure-aware chunking (REQ-RAG-03, research R-17).

Chunks never cross a heading: each one carries its heading path (`H1 > H2`) as `section`. Long
sections are packed into chunks of at most 800 tokens with an 80-token overlap; a Markdown table
is never split (a table larger than the limit becomes a chunk of its own).
"""

import re
from dataclasses import dataclass

MIN_TOKENS = 400
MAX_TOKENS = 800
OVERLAP_TOKENS = 80

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")


@dataclass(frozen=True)
class Chunk:
    section: str
    content: str


def count_tokens(text: str) -> int:
    # shortcut: whitespace words approximate model tokens (a BPE tokenizer would need a download
    # in the offline job); switch to a cached tiktoken encoding if sizes must be exact.
    return len(text.split())


def passage(title: str, section: str, content: str) -> str:
    """Text that is embedded, indexed by BM25 and reranked: the heading path gives context."""
    return f"{title}\n{section}\n{content}"


def _is_table(line: str) -> bool:
    return line.lstrip().startswith("|")


def _sections(text: str, title: str) -> list[tuple[str, list[str]]]:
    """Splits Markdown into (heading path, blocks); a block is a paragraph, list or table."""
    sections: list[tuple[str, list[str]]] = []
    path: list[tuple[int, str]] = []
    blocks: list[str] = []
    lines: list[str] = []

    def end_block() -> None:
        if lines:
            blocks.append("\n".join(lines))
            lines.clear()

    def end_section() -> None:
        end_block()
        if blocks:
            sections.append((" > ".join(h for _, h in path) or title, blocks.copy()))
            blocks.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _HEADING.match(line)
        if heading:
            end_section()
            level = len(heading.group(1))
            path = [(lvl, h) for lvl, h in path if lvl < level] + [(level, heading.group(2))]
        elif not line.strip():
            end_block()
        else:
            if lines and _is_table(lines[-1]) != _is_table(line):
                end_block()
            lines.append(line)
    end_section()
    return sections


def _pieces(block: str) -> list[tuple[str, bool]]:
    """(text, is_table). Text longer than one window is cut by words so that the overlap plus a
    piece always fits in MAX_TOKENS; tables stay whole."""
    if _is_table(block):
        return [(block, True)]
    words = block.split()
    size = MAX_TOKENS - OVERLAP_TOKENS
    if len(words) <= size:
        return [(block, False)]
    return [(" ".join(words[i : i + size]), False) for i in range(0, len(words), size)]


def _pack(pieces: list[tuple[str, bool]]) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    tail: list[str] = []  # words after the last table: the only text reused as overlap
    for text, is_table in pieces:
        n = count_tokens(text)
        if current and size + n > MAX_TOKENS:
            chunks.append("\n\n".join(current))
            overlap = tail[-OVERLAP_TOKENS:]
            current = [" ".join(overlap)] if overlap else []
            size, tail = len(overlap), list(overlap)
        current.append(text)
        size += n
        tail = [] if is_table else tail + text.split()
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_text(text: str, title: str) -> list[Chunk]:
    return [
        Chunk(section=section, content=content)
        for section, blocks in _sections(text, title)
        for content in _pack([p for block in blocks for p in _pieces(block)])
    ]
