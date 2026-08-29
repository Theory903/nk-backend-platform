from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

class ScimFilterError(ValueError):
    pass

class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    CO = "co"
    SW = "sw"
    EW = "ew"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    PR = "pr"

@dataclass(frozen=True, slots=True)
class FilterExpression:
    attribute: str
    operator: FilterOperator
    value: Any = None

@dataclass(frozen=True, slots=True)
class FilterGroup:
    operator: str
    children: tuple[Any, ...]

_TOKEN_RE = re.compile(
    r"""
    \s*
    (
        and\b |
        or\b |
        not\b |
        eq\b |
        ne\b |
        co\b |
        sw\b |
        ew\b |
        gt\b |
        ge\b |
        lt\b |
        le\b |
        pr\b |
        \(|\) |
        "[^"]*" |
        '[^']*' |
        [A-Za-z_][A-Za-z0-9_.:-]* |
        -?\d+(?:\.\d+)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

class ScimFilterParser:
    """
    Small SCIM filter parser supporting the operators normally needed
    for enterprise user provisioning.

    Examples:

        userName eq "john@example.com"
        externalId eq "abc"
        active eq true
        userName co "john"
        userName sw "john"
        active pr
        userName eq "john" and active eq true
    """

    def __init__(self, expression: str) -> None:
        self.expression = expression
        self.tokens = self._tokenize(expression)
        self.position = 0

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        tokens: list[str] = []
        offset = 0

        for match in _TOKEN_RE.finditer(value):
            if match.start() != offset and value[offset:match.start()].strip():
                raise ScimFilterError("invalid SCIM filter")

            tokens.append(match.group(1))
            offset = match.end()

        if value[offset:].strip():
            raise ScimFilterError("invalid SCIM filter")

        return tokens

    def parse(self) -> Any:
        if not self.tokens:
            raise ScimFilterError("empty filter")

        result = self._parse_or()

        if self.position != len(self.tokens):
            raise ScimFilterError("unexpected token in filter")

        return result

    def _peek(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _consume(self) -> str:
        token = self._peek()
        if token is None:
            raise ScimFilterError("unexpected end of filter")

        self.position += 1
        return token

    def _match(self, value: str) -> bool:
        token = self._peek()
        if token is not None and token.lower() == value.lower():
            self.position += 1
            return True
        return False

    def _parse_or(self) -> Any:
        left = self._parse_and()

        children = [left]

        while self._match("or"):
            children.append(self._parse_and())

        if len(children) == 1:
            return left

        return FilterGroup("or", tuple(children))

    def _parse_and(self) -> Any:
        left = self._parse_primary()

        children = [left]

        while self._match("and"):
            children.append(self._parse_primary())

        if len(children) == 1:
            return left

        return FilterGroup("and", tuple(children))

    def _parse_primary(self) -> Any:
        if self._match("("):
            expression = self._parse_or()

            if not self._match(")"):
                raise ScimFilterError("missing ')'")

            return expression

        return self._parse_expression()

    def _parse_expression(self) -> FilterExpression:
        attribute = self._consume()

        operator = self._consume().lower()

        try:
            op = FilterOperator(operator)
        except ValueError as exc:
            raise ScimFilterError(
                f"unsupported SCIM operator: {operator}",
            ) from exc

        if op is FilterOperator.PR:
            return FilterExpression(attribute, op)

        raw_value = self._consume()

        return FilterExpression(
            attribute=attribute,
            operator=op,
            value=self._parse_value(raw_value),
        )

    @staticmethod
    def _parse_value(value: str) -> Any:
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            return value[1:-1]

        lower = value.lower()

        if lower == "true":
            return True

        if lower == "false":
            return False

        if lower == "null":
            return None

        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

__all__ = [
    "ScimFilterError",
    "FilterOperator",
    "FilterExpression",
    "FilterGroup",
    "ScimFilterParser",
]

