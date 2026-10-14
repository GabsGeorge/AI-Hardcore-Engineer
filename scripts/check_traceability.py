"""Rastreabilidade REQ → tarefa → teste → commit (REQ-INF-04).

Lê os ``@pytest.mark.req("REQ-...")`` dos testes e cruza com os REQ-IDs citados em
``specs/001-multi-agent-support/tasks.md``. Gera ``docs/traceability.md`` com a tabela e
retorna código ≠ 0 quando algum REQ entregue (tarefa marcada ``[X]`` em tasks.md) não tem
pelo menos um teste associado.

Uso:
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests \
        python scripts/check_traceability.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
TASKS = ROOT / "specs" / "001-multi-agent-support" / "tasks.md"
OUT = ROOT / "docs" / "traceability.md"

_REQ_RE = re.compile(r"REQ-[A-Z]+-\d+")
_TASK_RE = re.compile(r"^- \[(X| )\] (T\d{3})[^(]*(\(([^)]*)\))?")


def _collect_test_reqs() -> dict[str, set[str]]:
    reqs: dict[str, set[str]] = defaultdict(set)
    for test_file in TESTS.rglob("test_*.py"):
        rel = test_file.relative_to(ROOT).as_posix()
        for line in test_file.read_text(encoding="utf-8").splitlines():
            if "pytest.mark.req" not in line:
                continue
            for req in _REQ_RE.findall(line):
                reqs[req].add(rel)
    return reqs


def _collect_tasks() -> list[tuple[str, bool, set[str]]]:
    tasks: list[tuple[str, bool, set[str]]] = []
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        m = _TASK_RE.match(line)
        if not m:
            continue
        done = m.group(1) == "X"
        tid = m.group(2)
        reqs = set(_REQ_RE.findall(line))
        tasks.append((tid, done, reqs))
    return tasks


def main() -> int:
    tests_by_req = _collect_test_reqs()
    tasks = _collect_tasks()

    all_reqs: set[str] = set(tests_by_req.keys())
    for _, _, reqs in tasks:
        all_reqs.update(reqs)

    rows: list[tuple[str, str, str, bool]] = []
    missing: list[str] = []
    for req in sorted(all_reqs):
        task_ids = sorted(tid for tid, _, reqs in tasks if req in reqs)
        delivered = any(done for tid, done, reqs in tasks if req in reqs and done)
        tests = sorted(tests_by_req.get(req, set()))
        rows.append((req, ", ".join(task_ids) or "-", ", ".join(tests) or "-", delivered))
        if delivered and not tests:
            missing.append(f"{req} (tarefas {', '.join(task_ids) or '-'})")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        f.write("# Rastreabilidade REQ → tarefa → teste\n\n")
        f.write("Gerado por `scripts/check_traceability.py` (REQ-INF-04).\n\n")
        f.write("| REQ | Tarefa(s) | Teste(s) | Entregue |\n")
        f.write("|---|---|---|---|\n")
        for req, tids, tests, delivered in rows:
            tick = "✅" if delivered else "⏳"
            f.write(f"| {req} | {tids} | {tests} | {tick} |\n")

    if missing:
        print("REQ entregues sem teste associado:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"rastreabilidade gerada em {OUT.relative_to(ROOT)} (REQs: {len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
