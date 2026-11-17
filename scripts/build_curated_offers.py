"""Turns the capture made by scripts/capture_offers.mjs into the curated Markdown that goes to the
knowledge base (src/app/rag/curated/).

Nothing here is typed by hand: every figure and every feature comes from the captured JSON, and the
text only reorganises it (no inference). The page builds its fee simulator with JavaScript, so the
regular crawler never receives it.

    python scripts/build_curated_offers.py [capture.json] [saida.md]
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CAPTURE = Path("src/app/rag/curated/todas-as-maquininhas.capture.json")
DEFAULT_OUTPUT = Path("src/app/rag/curated/todas-as-maquininhas.md")

_MACHINE = re.compile(r"^Get (Lite|Clássica|Smart|Mini|Tap)$")
_INSTALLMENT = re.compile(r"([\d.,]+)%\s*Crédito\s+(\d+)x")


@dataclass
class Card:
    name: str
    tagline: str = ""
    price_tokens: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)

    @property
    def price(self) -> str:
        text = " ".join(self.price_tokens)
        text = re.sub(r"(\d) ,(\d)", r"\1,\2", text)  # "R$ 5 ,90" -> "R$ 5,90"
        return re.sub(r"\s+/mês", "/mês", text).strip()

    @property
    def display_price(self) -> str:
        """The price as a reader would state it. "De: X Grátis" is free (X is the full value),
        "De: X Y/mês" is Y a month (X is the full value) and "Por: Y/mês" is Y a month."""
        free = re.fullmatch(r"De:\s*(R\$ [\d.,]+)\s+Grátis", self.price)
        if free:
            return f"Grátis (valor cheio {free.group(1)})"
        discounted = re.fullmatch(r"De:\s*(R\$ [\d.,]+)\s+(R\$ [\d.,]+/mês)", self.price)
        if discounted:
            return f"{discounted.group(2)} (valor cheio {discounted.group(1)})"
        by = re.fullmatch(r"Por:\s*(R\$ [\d.,]+/mês)", self.price)
        return by.group(1) if by else self.price


def parse_installments(raw: str) -> list[tuple[int, str]]:
    """[(2, "4,59%"), (3, "5,71%"), ...]: the page lists the rate first, then the label."""
    return [(int(n), f"{rate}%") for rate, n in _INSTALLMENT.findall(raw)]


def parse_cards(raw: str) -> list[Card]:
    cards: list[Card] = []
    current: Card | None = None
    stage = ""
    for line in (ln.strip() for ln in raw.splitlines()):
        if not line:
            continue
        if _MACHINE.match(line):
            current = Card(name=line)
            cards.append(current)
            stage = "tagline"
        elif current is None:
            continue
        elif stage == "tagline":
            current.tagline, stage = line, "price"
        elif stage == "price":
            if line.upper() == "DETALHES DA OFERTA":
                stage = "cta"
            else:
                current.price_tokens.append(line)
        elif stage == "cta":  # "ALUGAR GET ..." / "PEDIR GET ..."
            stage = "features"
        else:
            current.features.append(line)
    return cards


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _between(lines: list[str], start: str, end_prefixes: tuple[str, ...]) -> list[str]:
    if start not in lines:
        return []
    out: list[str] = []
    for line in lines[lines.index(start) + 1 :]:
        if line.startswith(end_prefixes):
            break
        out.append(line)
    return out


def _tier_rates(tier: dict[str, str]) -> list[tuple[str, str]]:
    rates = [("Débito", tier["debito"]), ("Crédito 1x", tier["credito1x"])]
    rates += [(f"Crédito {n}x", rate) for n, rate in parse_installments(tier["parcelas"])]
    return rates


def build(capture: dict) -> str:
    source = capture["fonte"].rstrip("/") + "/#offers-card"
    day = capture["capturadoEm"][:10]
    brands = " / ".join(capture.get("detalhes", {}).get("bandeiras", [])) or "Visa / Master"
    tiers = capture["faixas"]
    modal = _lines(capture.get("detalhes", {}).get("texto", ""))

    out = [
        "# Maquininhas Getnet: taxas por faixa de faturamento, preços e recursos",
        "",
        f"Fonte: {source} (campanha: {capture['titulo']}). Conteúdo capturado em {day} com um "
        "navegador, porque a página monta estas tabelas com JavaScript. As taxas são "
        f'"a partir de" e valem para a bandeira {brands}. Ofertas e taxas de campanha podem mudar.',
        "",
    ]

    # --- Taxas por faixa -----------------------------------------------------------------
    installments = [n for n, _ in parse_installments(tiers[0]["parcelas"])]
    header = ["Faixa de faturamento mensal", "Débito", "Crédito 1x"] + [
        f"{n}x" for n in installments
    ]
    out += [f"## Taxas de débito e crédito por faixa de faturamento mensal ({brands})", ""]
    out += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for tier in tiers:
        cells = [tier["label"], tier["debito"], tier["credito1x"]]
        cells += [rate for _, rate in parse_installments(tier["parcelas"])]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    for tier in tiers:
        out += [f"## Taxas na faixa {tier['label']} de faturamento mensal ({brands})", ""]
        out += [f"- {label}: {rate}" for label, rate in _tier_rates(tier)]
        out.append("")

    # --- Maquininhas e preços por faixa ---------------------------------------------------
    features: dict[str, list[str]] = {}
    taglines: dict[str, str] = {}
    shown: dict[str, dict[str, str]] = {}  # tier id -> machine -> price as displayed
    machines: list[str] = []
    for tier in tiers:
        cards = parse_cards(tier["cartoes"])
        out += [f"## Maquininhas e preços na faixa {tier['label']} de faturamento mensal", ""]
        if tier.get("descontoAluguel"):
            out += [f"- Desconto no aluguel exibido para esta faixa: {tier['descontoAluguel']}"]
        for card in cards:
            features.setdefault(card.name, card.features)
            taglines.setdefault(card.name, card.tagline)
            if card.name not in machines:
                machines.append(card.name)
            shown.setdefault(tier["id"], {})[card.name] = card.display_price
            out.append(f"- {card.name} ({card.tagline}): preço exibido: {card.display_price}")
        out.append("")

    # One table with every machine and tier side by side: the answer to "how much must I bill for
    # X to be free" is a comparison across tiers and must not depend on retrieving all of them.
    out += ["## Preço de cada maquininha por faixa de faturamento mensal", ""]
    head = ["Faixa de faturamento mensal", *machines]
    out += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for tier in tiers:
        row = [shown.get(tier["id"], {}).get(m, "não exibida nesta faixa") for m in machines]
        out.append("| " + " | ".join([tier["label"], *row]) + " |")
    out.append("")

    # The question a merchant asks is "how much must I bill for it to be free". Answer it in one
    # place, computed from the table: the first tier where each machine's price is "Grátis".
    free_lines: list[str] = []
    for machine in machines:
        for position, tier in enumerate(tiers):
            if shown.get(tier["id"], {}).get(machine, "").startswith("Grátis"):
                before = [
                    f"{t['label']}: {shown[t['id']][machine]}"
                    for t in tiers[:position]
                    if machine in shown.get(t["id"], {})
                ]
                line = (
                    f"- {machine}: aluguel grátis a partir da faixa {tier['label']} de "
                    "faturamento mensal, e também nas faixas maiores."
                )
                if before:
                    line += f" Nas faixas menores o preço exibido é: {'; '.join(before)}."
                free_lines.append(line)
                break
    if free_lines:
        out += ["## Quanto preciso faturar por mês para ganhar a maquininha de graça", ""]
        out += [*free_lines, ""]

    # --- Recursos de cada maquininha -------------------------------------------------------
    for name, items in features.items():
        out += [f"## {name}: recursos", "", f"{name}: {taglines[name]}.", ""]
        out += [f"- {item}" for item in items]
        out.append("")

    if "Get Clássica" in features and "Get Smart" in features:
        classic, smart = features["Get Clássica"], features["Get Smart"]
        out += ["## Get Clássica e Get Smart: o que cada cartão lista", ""]
        out += [f"- Get Clássica: {'; '.join(classic)}", f"- Get Smart: {'; '.join(smart)}"]
        out += [
            "- Esta lista reflete só o que a página mostra em cada cartão. A página não "
            "detalha todas as características: um item que não aparece no cartão de uma "
            "maquininha não significa que ela não o tenha.",
            "",
        ]

    # --- Pacote, isenção do aluguel e valor de utilização ----------------------------------
    perks = _between(modal, "Maquininha + conta integrada Getnet", ("Vendendo você",))
    if perks:
        out += ["## Benefícios do pacote maquininha + conta integrada", ""]
        out += [f"- {a}: {b}" for a, b in zip(perks[::2], perks[1::2], strict=False)]
        out.append("")

    free = _between(modal, "Vendendo você ganha máquina grátis", ("*Termos",))
    if free:
        out += ["## Qual maquininha sai com aluguel grátis, por faixa de faturamento", ""]
        out += [f"- {line.lstrip('*')}" if line.startswith("*") else f"- {line}" for line in free]
        out.append("")

    usage = _between(
        modal, "Caso não atinja os faturamentos do quadro acima, segue o valor de utilização:", ()
    )
    if usage:
        out += ["## Valor de utilização por mês quando o faturamento da faixa não é atingido", ""]
        out += [f"- {a}: {b}" for a, b in zip(usage[::2], usage[1::2], strict=False)]
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    capture_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CAPTURE
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    output_path.write_text(build(capture), encoding="utf-8", newline="\n")
    print(f"{capture_path} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
