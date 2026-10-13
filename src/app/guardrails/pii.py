"""PII masking (REQ-GR-02): CPF, CNPJ, Luhn-valid cards, e-mail and BR phone numbers.

Numbers are masked only when they pass their check digits, so amounts, codes and IDs survive.
"""

import re
from collections.abc import Callable

_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(
    r"\+55\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}(?!\d)"  # +55 51 99876-5432
    r"|\(\d{2}\)\s?9?\d{4}-?\d{4}(?!\d)"  # (51) 99876-5432
    r"|(?<!\d)\d{2}\s9\d{4}-\d{4}(?!\d)"  # 51 99876-5432
)


def _digits(text: str) -> list[int]:
    return [int(c) for c in text if c.isdigit()]


def _check_digit(digits: list[int], weights: list[int]) -> int:
    rest = sum(d * w for d, w in zip(digits, weights, strict=False)) % 11
    return 0 if rest < 2 else 11 - rest


def _valid_cpf(text: str) -> bool:
    d = _digits(text)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    return d[9] == _check_digit(d[:9], list(range(10, 1, -1))) and d[10] == _check_digit(
        d[:10], list(range(11, 1, -1))
    )


def _valid_cnpj(text: str) -> bool:
    d = _digits(text)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return d[12] == _check_digit(d[:12], w1) and d[13] == _check_digit(d[:13], [6, *w1])


def _valid_card(text: str) -> bool:
    d = _digits(text)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, digit in enumerate(reversed(d)):
        if i % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


# Phone runs before card so "+55 51 99876-5432" is never read as a 13-digit card number.
_RULES: list[tuple[str, str, re.Pattern[str], Callable[[str], bool]]] = [
    ("cnpj", "[CNPJ]", _CNPJ, _valid_cnpj),
    ("cpf", "[CPF]", _CPF, _valid_cpf),
    ("email", "[EMAIL]", _EMAIL, lambda _: True),
    ("phone", "[TELEFONE]", _PHONE, lambda _: True),
    ("card", "[CARTAO]", _CARD, _valid_card),
]


def mask(text: str) -> tuple[str, list[str]]:
    """Returns the masked text and the PII types found (each type once, in rule order)."""
    found: list[str] = []
    for kind, token, pattern, is_valid in _RULES:

        def _sub(
            m: re.Match[str], token: str = token, is_valid: Callable[[str], bool] = is_valid
        ) -> str:
            return token if is_valid(m.group()) else m.group()

        masked = pattern.sub(_sub, text)
        if masked != text:
            found.append(kind)
            text = masked
    return text, found
