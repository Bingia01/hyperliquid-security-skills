"""Rule expressions: a small, safe, statically typed language.

Syntax is a strict subset of Python expression syntax, parsed with ``ast`` and
interpreted by walking the tree; nothing is ever passed to ``eval``. Supported:

* namespaced references: ``market.open_interest_usd``, ``threshold.max_ratio``
* number, string and boolean literals (``true``/``false`` or ``True``/``False``)
* arithmetic ``+ - * /``, unary ``-``
* comparisons ``< <= > >= == !=``, ``in``/``not in`` (chains allowed)
* logic ``and``, ``or``, ``not``
* list literals ``['a', 'b']``
* functions: ``abs``, ``min``, ``max``, ``bps_diff``, ``to_bps``,
  ``count_true``, ``size``, ``difference``

Semantics:

* **Three-valued logic.** A reference with no value evaluates to ``UNKNOWN``.
  Arithmetic and comparisons involving ``UNKNOWN`` yield ``UNKNOWN``;
  ``and``/``or``/``not`` follow Kleene logic. A rule therefore reports
  "unknown" when it lacks data, instead of silently reporting "did not fire".
* **Division by zero.** ``x / 0`` is ``+inf`` or ``-inf`` for non-zero ``x``
  (zero depth means infinitely thin, which must trip a ratio threshold) and
  ``UNKNOWN`` for ``0 / 0``. NaN inputs are treated as ``UNKNOWN``.
* **Static typing.** ``check`` infers each sub-expression's kind and unit and
  rejects unknown names, unit mismatches, and string comparisons against values
  outside a reference's declared vocabulary.
"""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union

from .units import DIMENSIONLESS, Unit


class ExpressionError(ValueError):
    """Raised for syntax or type errors in an expression."""


class Kind(Enum):
    NUMBER = "number"
    BOOL = "bool"
    STRING = "string"
    LIST = "list"


@dataclass(frozen=True)
class Type:
    kind: Kind
    unit: Unit | None = None  # numbers only
    element: Type | None = None  # lists only; None for an empty list literal
    values: frozenset[str] | None = None  # closed string vocabulary, if any
    any_unit: bool = False  # the literal 0, compatible with every unit

    def describe(self) -> str:
        if self.kind is Kind.NUMBER:
            return f"number[{'any' if self.any_unit else self.unit}]"
        if self.kind is Kind.LIST:
            return f"list[{self.element.describe() if self.element else 'empty'}]"
        return str(self.kind.value)


BOOL = Type(Kind.BOOL)
STRING = Type(Kind.STRING)


def number(unit: Unit) -> Type:
    return Type(Kind.NUMBER, unit=unit)


class _Unknown:
    """Sentinel for a value that could not be determined."""

    _instance: _Unknown | None = None

    def __new__(cls) -> _Unknown:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        raise TypeError("UNKNOWN has no truth value; use three-valued helpers")


UNKNOWN = _Unknown()

Value = Union[float, int, bool, str, list[Any], _Unknown]


@dataclass(frozen=True)
class Expression:
    source: str
    tree: ast.expr
    references: frozenset[str]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_BOOL_NAMES = {"true": True, "false": False}
FUNCTIONS = frozenset(
    {"abs", "min", "max", "bps_diff", "to_bps", "count_true", "size", "difference"}
)
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Compare,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Load,
)


_REFERENCE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def _check_reference_shape(name: str, source: str) -> None:
    if not _REFERENCE.match(name):
        raise ExpressionError(
            f"reference {name!r} in {source!r} must have the form namespace.name "
            "(lowercase letters, digits, underscores)"
        )


def dotted_name(node: ast.expr) -> str | None:
    """Return ``a.b.c`` for an attribute chain rooted at a Name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name) and parts:
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def parse(source: str) -> Expression:
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError("expression must be a non-empty string")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"syntax error in {source!r}: {exc.msg}") from None
    references: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"{type(node).__name__} is not allowed in expressions: {source!r}"
            )
        if isinstance(node, ast.Attribute):
            name = dotted_name(node)
            if name is None:
                raise ExpressionError(f"unsupported attribute access in {source!r}")
            _check_reference_shape(name, source)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise ExpressionError(
                    f"unknown function in {source!r}; allowed: {sorted(FUNCTIONS)}"
                )
            if node.keywords:
                raise ExpressionError(f"keyword arguments are not allowed: {source!r}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (bool, int, float, str)):
            raise ExpressionError(f"unsupported literal {node.value!r} in {source!r}")
    # Collect references from outermost attribute chains only.
    _collect_references(tree.body, references, source)
    return Expression(source=source.strip(), tree=tree.body, references=frozenset(references))


def _collect_references(node: ast.AST, out: set[str], source: str) -> None:
    if isinstance(node, ast.Attribute):
        name = dotted_name(node)
        assert name is not None
        out.add(name)
        return
    if isinstance(node, ast.Call):
        for arg in node.args:
            _collect_references(arg, out, source)
        return
    if isinstance(node, ast.Name):
        if node.id not in _BOOL_NAMES:
            raise ExpressionError(
                f"bare name {node.id!r} in {source!r}; references must be namespaced "
                "(e.g. market.mark_price or threshold.max_ratio)"
            )
        return
    for child in ast.iter_child_nodes(node):
        _collect_references(child, out, source)


# --------------------------------------------------------------------------
# Static type checking
# --------------------------------------------------------------------------

Resolver = Callable[[str], Union[Type, None]]


def check(expression: Expression, resolve: Resolver) -> Type:
    """Infer the type of ``expression``; raise ExpressionError on any problem."""
    return _Checker(expression.source, resolve).visit(expression.tree)


class _Checker:
    def __init__(self, source: str, resolve: Resolver) -> None:
        self.source = source
        self.resolve = resolve

    def fail(self, message: str) -> ExpressionError:
        return ExpressionError(f"{message} in {self.source!r}")

    def visit(self, node: ast.expr) -> Type:
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            raise self.fail(f"unsupported syntax {type(node).__name__}")
        result: Type = method(node)
        return result

    def visit_Constant(self, node: ast.Constant) -> Type:
        value = node.value
        if isinstance(value, bool):
            return BOOL
        if isinstance(value, (int, float)):
            return Type(Kind.NUMBER, unit=DIMENSIONLESS, any_unit=value == 0)
        return STRING

    def visit_Name(self, node: ast.Name) -> Type:
        if node.id in _BOOL_NAMES:
            return BOOL
        raise self.fail(f"bare name {node.id!r}")

    def visit_Attribute(self, node: ast.Attribute) -> Type:
        name = dotted_name(node)
        resolved = self.resolve(name) if name else None
        if resolved is None:
            raise self.fail(f"unknown reference {name!r}")
        return resolved

    def visit_BoolOp(self, node: ast.BoolOp) -> Type:
        for operand in node.values:
            self.expect(operand, Kind.BOOL, "logical operand")
        return BOOL

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Type:
        if isinstance(node.op, ast.Not):
            self.expect(node.operand, Kind.BOOL, "operand of 'not'")
            return BOOL
        operand = self.expect(node.operand, Kind.NUMBER, "operand of unary '-'")
        return operand

    def visit_BinOp(self, node: ast.BinOp) -> Type:
        left = self.expect(node.left, Kind.NUMBER, "arithmetic operand")
        right = self.expect(node.right, Kind.NUMBER, "arithmetic operand")
        if isinstance(node.op, (ast.Add, ast.Sub)):
            return number(self.unify(left, right, "+/-"))
        assert left.unit is not None and right.unit is not None
        if isinstance(node.op, ast.Mult):
            return number(left.unit * right.unit)
        return number(left.unit / right.unit)

    def visit_Compare(self, node: ast.Compare) -> Type:
        operands = [node.left, *node.comparators]
        for op, left_node, right_node in zip(node.ops, operands, operands[1:], strict=False):
            left, right = self.visit(left_node), self.visit(right_node)
            if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                if left.kind is not Kind.NUMBER or right.kind is not Kind.NUMBER:
                    raise self.fail(
                        f"ordering comparison needs numbers, got {left.describe()} "
                        f"and {right.describe()}"
                    )
                self.unify(left, right, "comparison")
            elif isinstance(op, (ast.Eq, ast.NotEq)):
                if left.kind is not right.kind:
                    raise self.fail(f"cannot compare {left.describe()} with {right.describe()}")
                if left.kind is Kind.NUMBER:
                    self.unify(left, right, "comparison")
                if left.kind is Kind.STRING:
                    self.check_vocabulary(left, right_node)
                    self.check_vocabulary(right, left_node)
            else:  # In / NotIn
                if right.kind is not Kind.LIST:
                    raise self.fail(f"right side of 'in' must be a list, got {right.describe()}")
                if right.element is not None and right.element.kind is not left.kind:
                    raise self.fail(f"'in' compares {left.describe()} against {right.describe()}")
                if left.kind is Kind.STRING and isinstance(right_node, (ast.List, ast.Tuple)):
                    for element in right_node.elts:
                        self.check_vocabulary(left, element)
        return BOOL

    def visit_List(self, node: ast.List) -> Type:
        return self.sequence(node.elts)

    def visit_Tuple(self, node: ast.Tuple) -> Type:
        return self.sequence(node.elts)

    def sequence(self, elements: Sequence[ast.expr]) -> Type:
        types = [self.visit(e) for e in elements]
        if not types:
            return Type(Kind.LIST, element=None)
        first = types[0]
        for other in types[1:]:
            if other.kind is not first.kind:
                raise self.fail("list elements must share one kind")
            if first.kind is Kind.NUMBER:
                self.unify(first, other, "list element")
        return Type(Kind.LIST, element=first)

    def visit_Call(self, node: ast.Call) -> Type:
        assert isinstance(node.func, ast.Name)
        name, args = node.func.id, node.args
        if name == "abs":
            self.arity(name, args, 1)
            return self.expect(args[0], Kind.NUMBER, "abs argument")
        if name in ("min", "max"):
            if len(args) == 1:
                lst = self.expect(args[0], Kind.LIST, f"{name} argument")
                if lst.element is None or lst.element.kind is not Kind.NUMBER:
                    raise self.fail(f"{name}(list) needs a list of numbers")
                return lst.element
            if not args:
                raise self.fail(f"{name} needs arguments")
            types = [self.expect(a, Kind.NUMBER, f"{name} argument") for a in args]
            unit = types[0]
            for other in types[1:]:
                unit = number(self.unify(unit, other, name))
            return unit
        if name == "bps_diff":
            self.arity(name, args, 2)
            a = self.expect(args[0], Kind.NUMBER, "bps_diff argument")
            b = self.expect(args[1], Kind.NUMBER, "bps_diff argument")
            self.unify(a, b, "bps_diff")
            return number(Unit.parse("bps"))
        if name == "to_bps":
            self.arity(name, args, 1)
            a = self.expect(args[0], Kind.NUMBER, "to_bps argument")
            if not (a.any_unit or (a.unit is not None and a.unit.is_dimensionless)):
                raise self.fail(f"to_bps needs a dimensionless ratio, got {a.describe()}")
            return number(Unit.parse("bps"))
        if name == "count_true":
            self.arity(name, args, 1)
            lst = self.expect(args[0], Kind.LIST, "count_true argument")
            if lst.element is not None and lst.element.kind is not Kind.BOOL:
                raise self.fail("count_true needs a list of booleans")
            return number(Unit.parse("count"))
        if name == "size":
            self.arity(name, args, 1)
            self.expect(args[0], Kind.LIST, "size argument")
            return number(Unit.parse("count"))
        if name == "difference":
            self.arity(name, args, 2)
            a = self.expect(args[0], Kind.LIST, "difference argument")
            b = self.expect(args[1], Kind.LIST, "difference argument")
            if a.element and b.element and a.element.kind is not b.element.kind:
                raise self.fail("difference needs lists of the same kind")
            return a
        raise self.fail(f"unknown function {name!r}")  # pragma: no cover

    # helpers -------------------------------------------------------------

    def expect(self, node: ast.expr, kind: Kind, what: str) -> Type:
        found = self.visit(node)
        if found.kind is not kind:
            raise self.fail(f"{what} must be {kind.value}, got {found.describe()}")
        return found

    def unify(self, a: Type, b: Type, what: str) -> Unit:
        if a.any_unit:
            assert b.unit is not None
            return b.unit
        if b.any_unit:
            assert a.unit is not None
            return a.unit
        if a.unit != b.unit:
            raise self.fail(f"unit mismatch in {what}: {a.unit} vs {b.unit}")
        assert a.unit is not None
        return a.unit

    def arity(self, name: str, args: Sequence[ast.expr], count: int) -> None:
        if len(args) != count:
            raise self.fail(f"{name} takes {count} argument(s), got {len(args)}")

    def check_vocabulary(self, declared: Type, literal_node: ast.expr) -> None:
        if (
            declared.values is not None
            and isinstance(literal_node, ast.Constant)
            and isinstance(literal_node.value, str)
            and literal_node.value not in declared.values
        ):
            raise self.fail(
                f"{literal_node.value!r} is not an allowed value; "
                f"allowed: {sorted(declared.values)}"
            )


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

Lookup = Callable[[str], Value]


class EvaluationError(RuntimeError):
    """Raised when runtime data has the wrong type (a snapshot defect)."""


def evaluate(expression: Expression, lookup: Lookup) -> Value:
    return _Evaluator(expression.source, lookup).visit(expression.tree)


def kleene_and(values: Sequence[Value]) -> Value:
    if any(v is False for v in values):
        return False
    if any(v is UNKNOWN for v in values):
        return UNKNOWN
    return True


def kleene_or(values: Sequence[Value]) -> Value:
    if any(v is True for v in values):
        return True
    if any(v is UNKNOWN for v in values):
        return UNKNOWN
    return False


def kleene_not(value: Value) -> Value:
    if value is UNKNOWN:
        return UNKNOWN
    return not value


class _Evaluator:
    def __init__(self, source: str, lookup: Lookup) -> None:
        self.source = source
        self.lookup = lookup

    def visit(self, node: ast.expr) -> Value:
        method = getattr(self, f"visit_{type(node).__name__}")
        result: Value = method(node)
        return result

    def number(self, value: Value) -> float | _Unknown:
        if value is UNKNOWN:
            return UNKNOWN
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EvaluationError(f"expected a number, got {value!r} in {self.source!r}")
        if isinstance(value, float) and math.isnan(value):
            return UNKNOWN
        return float(value)

    def boolean(self, value: Value) -> bool | _Unknown:
        if value is UNKNOWN or isinstance(value, bool):
            return value
        raise EvaluationError(f"expected a boolean, got {value!r} in {self.source!r}")

    def visit_Constant(self, node: ast.Constant) -> Value:
        value = node.value
        if isinstance(value, (bool, int, float, str)):
            return value
        raise EvaluationError(f"unsupported literal {value!r}")  # parse() rejects these

    def visit_Name(self, node: ast.Name) -> Value:
        return _BOOL_NAMES[node.id]

    def visit_Attribute(self, node: ast.Attribute) -> Value:
        name = dotted_name(node)
        assert name is not None
        return self.lookup(name)

    def visit_BoolOp(self, node: ast.BoolOp) -> Value:
        # Evaluate every operand so the caller learns about all missing inputs.
        values = [self.boolean(self.visit(v)) for v in node.values]
        return kleene_and(values) if isinstance(node.op, ast.And) else kleene_or(values)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Value:
        if isinstance(node.op, ast.Not):
            return kleene_not(self.boolean(self.visit(node.operand)))
        value = self.number(self.visit(node.operand))
        return UNKNOWN if isinstance(value, _Unknown) else -value

    def visit_BinOp(self, node: ast.BinOp) -> Value:
        left = self.number(self.visit(node.left))
        right = self.number(self.visit(node.right))
        if isinstance(left, _Unknown) or isinstance(right, _Unknown):
            return UNKNOWN
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return divide(left, right)

    def visit_Compare(self, node: ast.Compare) -> Value:
        operands = [self.visit(node.left), *(self.visit(c) for c in node.comparators)]
        results: list[Value] = []
        for op, left, right in zip(node.ops, operands, operands[1:], strict=False):
            results.append(self.compare(op, left, right))
        return kleene_and(results)

    def compare(self, op: ast.cmpop, left: Value, right: Value) -> Value:
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        if isinstance(op, (ast.In, ast.NotIn)):
            if not isinstance(right, list):
                raise EvaluationError(f"'in' needs a list in {self.source!r}")
            found = left in right
            return found if isinstance(op, ast.In) else not found
        if isinstance(op, (ast.Eq, ast.NotEq)):
            if isinstance(left, (int, float)) and not isinstance(left, bool):
                left_n, right_n = self.number(left), self.number(right)
                if left_n is UNKNOWN or right_n is UNKNOWN:
                    return UNKNOWN
                equal = left_n == right_n
            else:
                equal = left == right
            return equal if isinstance(op, ast.Eq) else not equal
        a, b = self.number(left), self.number(right)
        if isinstance(a, _Unknown) or isinstance(b, _Unknown):
            return UNKNOWN
        if isinstance(op, ast.Lt):
            return a < b
        if isinstance(op, ast.LtE):
            return a <= b
        if isinstance(op, ast.Gt):
            return a > b
        return a >= b

    def visit_List(self, node: ast.List) -> Value:
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Value:
        return [self.visit(e) for e in node.elts]

    def visit_Call(self, node: ast.Call) -> Value:
        assert isinstance(node.func, ast.Name)
        name = node.func.id
        args = [self.visit(a) for a in node.args]
        if any(a is UNKNOWN for a in args):
            return UNKNOWN
        if name == "abs":
            value = self.number(args[0])
            return UNKNOWN if isinstance(value, _Unknown) else abs(value)
        if name in ("min", "max"):
            items = args[0] if len(args) == 1 else args
            if not isinstance(items, list) or not items:
                return UNKNOWN
            numbers = [self.number(v) for v in items]
            known = [v for v in numbers if not isinstance(v, _Unknown)]
            if len(known) != len(numbers):
                return UNKNOWN
            return min(known) if name == "min" else max(known)
        if name == "bps_diff":
            a, b = self.number(args[0]), self.number(args[1])
            if isinstance(a, _Unknown) or isinstance(b, _Unknown):
                return UNKNOWN
            return divide(abs(a - b) * 10_000.0, abs(b))
        if name == "to_bps":
            a = self.number(args[0])
            return UNKNOWN if isinstance(a, _Unknown) else a * 10_000.0
        if name == "count_true":
            items = self.as_list(args[0])
            if any(i is UNKNOWN for i in items):
                return UNKNOWN
            return float(sum(1 for i in items if self.boolean(i) is True))
        if name == "size":
            return float(len(self.as_list(args[0])))
        if name == "difference":
            exclude = self.as_list(args[1])
            return [i for i in self.as_list(args[0]) if i not in exclude]
        raise EvaluationError(f"unknown function {name!r}")  # pragma: no cover

    def as_list(self, value: Value) -> list[Any]:
        if not isinstance(value, list):
            raise EvaluationError(f"expected a list, got {value!r} in {self.source!r}")
        return value


def divide(numerator: float, denominator: float) -> float | _Unknown:
    if denominator == 0:
        if numerator == 0:
            return UNKNOWN
        return math.inf if numerator > 0 else -math.inf
    return numerator / denominator
