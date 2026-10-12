"""Dimensional units for rule expressions.

A unit is a product of base dimensions with integer exponents, e.g. ``usd``,
``usd/seconds`` or dimensionless (``ratio``). Units are checked statically so
that a rule cannot compare a ratio to basis points, or a market-wide notional
to a count, without an explicit conversion.

Basis points are deliberately a base dimension rather than "ratio x 10000":
mixing the two silently is the most common unit bug in risk rules, so the
conversion must be written out with ``to_bps(...)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BASE_DIMENSIONS = frozenset({"usd", "bps", "seconds", "count", "sigma", "base_asset"})

_ATOM = re.compile(r"^[a-z_]+$")


class UnitError(ValueError):
    """Raised for malformed unit strings or invalid unit arithmetic."""


@dataclass(frozen=True)
class Unit:
    """An immutable product of base dimensions, e.g. {"usd": 1, "seconds": -1}."""

    exponents: tuple[tuple[str, int], ...] = field(default=())

    @staticmethod
    def of(mapping: dict[str, int]) -> Unit:
        cleaned = tuple(sorted((k, v) for k, v in mapping.items() if v != 0))
        return Unit(cleaned)

    @staticmethod
    def parse(text: str) -> Unit:
        """Parse ``"usd"``, ``"usd/seconds"``, ``"ratio"`` (dimensionless)."""
        text = text.strip()
        if text in ("ratio", "dimensionless", "1"):
            return DIMENSIONLESS
        parts = text.split("/")
        if len(parts) > 2:
            raise UnitError(f"unit {text!r}: at most one '/' is allowed")
        exponents: dict[str, int] = {}
        for sign, chunk in zip((1, -1), parts, strict=False):
            for atom in chunk.split("*"):
                atom = atom.strip()
                if not _ATOM.match(atom) or atom not in BASE_DIMENSIONS:
                    raise UnitError(
                        f"unit {text!r}: unknown dimension {atom!r}; "
                        f"allowed: {sorted(BASE_DIMENSIONS)} or 'ratio'"
                    )
                exponents[atom] = exponents.get(atom, 0) + sign
        return Unit.of(exponents)

    def _as_dict(self) -> dict[str, int]:
        return dict(self.exponents)

    def __mul__(self, other: Unit) -> Unit:
        merged = self._as_dict()
        for k, v in other.exponents:
            merged[k] = merged.get(k, 0) + v
        return Unit.of(merged)

    def __truediv__(self, other: Unit) -> Unit:
        merged = self._as_dict()
        for k, v in other.exponents:
            merged[k] = merged.get(k, 0) - v
        return Unit.of(merged)

    @property
    def is_dimensionless(self) -> bool:
        return not self.exponents

    def __str__(self) -> str:
        if self.is_dimensionless:
            return "ratio"
        num = [k if v == 1 else f"{k}^{v}" for k, v in self.exponents if v > 0]
        den = [k if v == -1 else f"{k}^{-v}" for k, v in self.exponents if v < 0]
        top = "*".join(num) if num else "1"
        return f"{top}/{'*'.join(den)}" if den else top


DIMENSIONLESS = Unit()
