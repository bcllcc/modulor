"""Safe math-expression compiler for implicit (SDF) modeling.

Agents describe a solid as a scalar field over x, y, z — the solid is the
region where the expression is POSITIVE. Only whitelisted AST nodes and
functions are allowed; there is no access to builtins, attributes,
subscripts, comprehensions or names beyond x/y/z and the constants below.

Example fields:
  sphere of radius r at origin:   r - length(x, y, z)
  box (rounded by k):             k - length(max(abs(x)-a,0), max(abs(y)-b,0), max(abs(z)-c,0))
  smooth union of two fields:     smax(f1, f2, k)
  gyroid shell:                   0.6 - abs(sin(x)*cos(y) + sin(y)*cos(z) + sin(z)*cos(x))
"""
from __future__ import annotations

import ast
import math

from .errors import CadError


def _length(*args) -> float:
    return math.sqrt(sum(a * a for a in args))


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _mix(a, b, t):
    return a + (b - a) * t


def _smin(a, b, k):
    """Polynomial smooth minimum (blends SDF surfaces over distance k)."""
    if k <= 0:
        return min(a, b)
    h = _clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return _mix(b, a, h) - k * h * (1.0 - h)


def _smax(a, b, k):
    return -_smin(-a, -b, k)


FUNCS: dict[str, object] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "sqrt": math.sqrt, "exp": math.exp,
    "log": math.log, "floor": math.floor, "ceil": math.ceil,
    "abs": abs, "min": min, "max": max, "pow": pow,
    "length": _length, "clamp": _clamp, "mix": _mix,
    "smin": _smin, "smax": _smax, "mod": math.fmod, "hypot": math.hypot,
}

NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
                   ast.FloorDiv)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)


def _check(node: ast.AST, names, funcs):
    if isinstance(node, ast.Expression):
        _check(node.body, names, funcs)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str)):
            raise CadError("bad_expr", f"constant {node.value!r} not allowed")
    elif isinstance(node, ast.Name):
        if node.id not in names and node.id not in funcs:
            close = [n for n in (*names, *funcs) if n.startswith(node.id[:2])]
            raise CadError("bad_expr", f"unknown name {node.id!r}",
                           hint=f"available: {sorted(names)[:30]}"
                                + (f"; similar: {close[:3]}" if close else ""))
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise CadError("bad_expr",
                           f"operator {type(node.op).__name__} not allowed")
        _check(node.left, names, funcs)
        _check(node.right, names, funcs)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY):
            raise CadError("bad_expr",
                           f"operator {type(node.op).__name__} not allowed")
        _check(node.operand, names, funcs)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in funcs:
            raise CadError("bad_expr", "only whitelisted function calls allowed",
                           hint=f"functions: {sorted(funcs)}")
        if node.keywords:
            raise CadError("bad_expr", "keyword arguments not allowed")
        for a in node.args:
            _check(a, names, funcs)
    else:
        raise CadError("bad_expr",
                       f"{type(node).__name__} not allowed in expressions",
                       hint="plain math only: numbers, names, + - * / ** %, "
                            "and whitelisted functions")


def _parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip():
        raise CadError("bad_expr", "empty expression")
    if len(expr) > 4000:
        raise CadError("bad_expr", "expression too long")
    try:
        return ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CadError("bad_expr", f"syntax error in {expr!r}: {e.msg}",
                       hint=f"at offset {e.offset}")


def compile_field(expr: str):
    """Compile an expression string to a fast f(x, y, z) -> float."""
    tree = _parse(expr)
    _check(tree, names={"x", "y", "z", *NAMES}, funcs=set(FUNCS))
    code = compile(tree, "<field>", "eval")
    env = {"__builtins__": {}, **FUNCS, **NAMES}

    def f(x: float, y: float, z: float) -> float:
        return eval(code, env, {"x": x, "y": y, "z": z})

    return f


def eval_expr(expr: str, extra_names: dict | None = None,
              extra_funcs: dict | None = None) -> float:
    """Evaluate a parameter expression (document params, level()/grid_x()...).

    Used wherever an op accepts a number and receives a string instead.
    """
    extra_names = extra_names or {}
    extra_funcs = extra_funcs or {}
    tree = _parse(expr)
    _check(tree, names={*NAMES, *extra_names},
           funcs={*FUNCS, *extra_funcs})
    code = compile(tree, "<param>", "eval")
    env = {"__builtins__": {}, **FUNCS, **NAMES,
           **extra_names, **extra_funcs}
    try:
        v = eval(code, env, {})
    except (ValueError, ZeroDivisionError, OverflowError, TypeError) as e:
        raise CadError("bad_expr", f"expression {expr!r} failed: {e}")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CadError("bad_expr",
                       f"expression {expr!r} did not produce a number")
    return float(v)
