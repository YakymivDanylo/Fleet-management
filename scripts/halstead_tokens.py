"""Token-based Halstead measures using the definitions from the lab assignment.

radon's ``hal`` command counts only AST operators (arithmetic, boolean, comparison), so its
eta1 stays tiny. The lab defines operators as keywords + operation symbols + delimiters and
operands as names + constants + strings; this script implements exactly that on top of the
stdlib ``tokenize`` module so both views can be reported side by side.

    python scripts/halstead_tokens.py src/fleet_management/resilience.py
    python scripts/halstead_tokens.py --functions src/fleet_management/services/rental_service.py
    python scripts/halstead_tokens.py --total src/fleet_management

Counting rules:
  operators: keyword tokens (``def``, ``if``, ``and``...) and every OP token (``=``, ``(``, ``,``)
  operands:  identifiers, numbers, strings (each f-string text chunk is one operand)
  skipped:   comments, whitespace/indent tokens, docstrings
"""

import argparse
import ast
import io
import keyword
import math
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SKIPPED = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
    tokenize.ENCODING,
    tokenize.FSTRING_START,
    tokenize.FSTRING_END,
}
OPERAND_TYPES = {tokenize.NUMBER, tokenize.STRING, tokenize.FSTRING_MIDDLE}


@dataclass
class Measures:
    operators: Counter
    operands: Counter

    @property
    def eta1(self) -> int:
        return len(self.operators)

    @property
    def eta2(self) -> int:
        return len(self.operands)

    @property
    def n1(self) -> int:
        return sum(self.operators.values())

    @property
    def n2(self) -> int:
        return sum(self.operands.values())

    @property
    def vocabulary(self) -> int:
        return self.eta1 + self.eta2

    @property
    def length(self) -> int:
        return self.n1 + self.n2

    @property
    def volume(self) -> float:
        return self.length * math.log2(self.vocabulary) if self.vocabulary > 1 else 0.0

    @property
    def difficulty(self) -> float:
        return self.eta1 / 2 * self.n2 / self.eta2 if self.eta2 else 0.0

    @property
    def effort(self) -> float:
        return self.volume * self.difficulty


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def measure(source: str, first_line: int = 1, last_line: int | None = None) -> Measures:
    skip_lines = docstring_lines(ast.parse(source))
    last_line = last_line or source.count("\n") + 2
    operators: Counter = Counter()
    operands: Counter = Counter()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        line = tok.start[0]
        if tok.type in SKIPPED or line in skip_lines or not first_line <= line <= last_line:
            continue
        if tok.type == tokenize.NAME and keyword.iskeyword(tok.string):
            operators[tok.string] += 1
        elif tok.type == tokenize.NAME or tok.type in OPERAND_TYPES:
            operands[tok.string] += 1
        elif tok.type == tokenize.OP:
            operators[tok.string] += 1
    return Measures(operators, operands)


def function_ranges(source: str) -> list[tuple[str, int, int]]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.append((node.name, node.lineno, node.end_lineno))
    return sorted(found, key=lambda item: item[1])


def row(label: str, m: Measures, loc: int | None = None) -> str:
    tail = f" {loc:>5}" if loc is not None else ""
    return (
        f"{label:<44} {m.eta1:>4} {m.eta2:>4} {m.n1:>5} {m.n2:>5} {m.vocabulary:>5} "
        f"{m.length:>6} {m.volume:>9.1f} {m.difficulty:>7.2f} {m.effort:>11.1f}{tail}"
    )


HEADER = (
    f"{'unit':<44} {'n1':>4} {'n2':>4} {'N1':>5} {'N2':>5} {'n':>5} {'N':>6} "
    f"{'V':>9} {'D':>7} {'E':>11}"
)


def python_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Token-based Halstead measures (lab definition).")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--functions", action="store_true", help="per-function rows")
    parser.add_argument("--total", action="store_true", help="also print one global row")
    args = parser.parse_args()

    files = python_files(args.paths)
    total = Measures(Counter(), Counter())
    print(HEADER + ("   LOC" if not args.functions else ""))
    for file in files:
        source = file.read_text(encoding="utf-8")
        if args.functions:
            print(f"# {file.as_posix()}")
            for name, start, end in function_ranges(source):
                print(row(f"  {name} ({start}-{end})", measure(source, start, end)))
            continue
        m = measure(source)
        total.operators.update(m.operators)
        total.operands.update(m.operands)
        print(row(file.as_posix(), m, len(source.splitlines())))
    if args.total and not args.functions:
        print(row("TOTAL (global vocabulary)", total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
