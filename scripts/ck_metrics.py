"""CK (Chidamber-Kemerer), Lorenz-Kidd and MOOD metrics for a Python source tree (Lab 8).

SonarQube has no class-level object-design metrics for Python (no class_complexity,
coupling_between_objects, lcom4 or dit), so the numbers come from this AST analyser. Its output
mimics the shape of SonarQube's ``api/measures/component`` response so that the report tables can
be produced by parsing JSON the same way for both sources.

Usage:
    python scripts/ck_metrics.py component src/fleet_management/services/rental_service.py
    python scripts/ck_metrics.py class     src/fleet_management/lab8/x.py ClassName
    python scripts/ck_metrics.py mood      src/fleet_management
    python scripts/ck_metrics.py table     src/fleet_management/lab8     # every class, as a table

Definitions (documented because CK metrics vary between tools):
    WMC   sum of McCabe complexity of the methods of the class (class_complexity)
    CBO   distinct other classes/modules the class refers to: imported names and module-level
          classes of the analysed tree used in its body (builtins, typing helpers excluded)
    RFC   methods of the class + distinct callee names invoked from them
    LCOM4 connected components of the method graph (edge = shared self.attribute or a call between
          methods); constructors and dunders are ignored. 1 is ideal, higher means "split me"
    LCOM  Henderson-Sellers LCOM* in [0, 1]: (mean(methods touching an attribute) - m) / (1 - m);
          0 is ideal cohesion
    DIT   depth of inheritance tree, ``object`` is depth 0, so a plain class has DIT 1; a base
          class that is not part of the analysed tree counts as one extra level
    PIM   public interface size: public methods, inherited ones included
    NMO   number of methods overridden from a project ancestor (Lorenz-Kidd)
    NMA   number of methods added by the class (Lorenz-Kidd)
"""

from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_NAMES = frozenset(
    {
        "self", "cls", "super", "object", "int", "str", "float", "bool", "list", "dict", "set",
        "tuple", "bytes", "len", "range", "enumerate", "zip", "sum", "min", "max", "abs", "round",
        "sorted", "isinstance", "print", "any", "all", "map", "filter", "reversed", "type",
        "None", "True", "False", "Exception", "ValueError", "TypeError", "KeyError",
        "RuntimeError", "NotImplementedError", "annotations", "Any", "Optional", "Callable",
        "Self", "ClassVar", "Final", "Literal", "TypeVar", "Generic", "Protocol", "Iterable",
        "Iterator", "Sequence", "Mapping", "frozenset", "getattr", "setattr", "hasattr",
        "dataclass",
    }
)  # fmt: skip


EXCLUDED_DIRS = set(filter(None, os.environ.get("CK_EXCLUDE", "").split(",")))


@dataclass
class ClassInfo:
    name: str
    path: Path
    node: ast.ClassDef
    bases: list[str]
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=dict)
    class_attrs: set[str] = field(default_factory=set)


def _complexity(fn: ast.AST) -> int:
    score = 1
    for node in ast.walk(fn):
        if isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While | ast.IfExp):
            score += 1
        elif isinstance(node, ast.ExceptHandler | ast.Assert):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            score += 1
    return score


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names)
    return names - IGNORED_NAMES


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _base_name(base: ast.expr) -> str:
    return ast.unparse(base).split(".")[-1].split("[")[0]


def _make_class(node: ast.ClassDef, path: Path) -> ClassInfo:
    info = ClassInfo(node.name, path, node, [_base_name(b) for b in node.bases])
    for stmt in node.body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            info.methods[stmt.name] = stmt
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            info.class_attrs.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            info.class_attrs.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
    return info


class Project:
    """All classes found under a directory (or in one file), indexed by name."""

    def __init__(self, root: Path):
        self.root = root
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        self.classes: dict[str, ClassInfo] = {}
        self.imports: dict[Path, set[str]] = {}
        for path in files:
            if "__pycache__" in path.parts or set(path.parts) & EXCLUDED_DIRS:
                continue
            tree = _parse(path)
            self.imports[path] = _imported_names(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.classes.setdefault(node.name, _make_class(node, path))

    # ---- inheritance -------------------------------------------------------------------------
    def ancestors(self, info: ClassInfo) -> list[ClassInfo]:
        found: list[ClassInfo] = []
        queue = list(info.bases)
        while queue:
            base = self.classes.get(queue.pop(0))
            if base is not None and base not in found:
                found.append(base)
                queue.extend(base.bases)
        return found

    def dit(self, info: ClassInfo, _seen: frozenset[str] = frozenset()) -> int:
        if not info.bases or info.name in _seen:
            return 1
        depths = []
        for base in info.bases:
            if base in self.classes:
                depths.append(self.dit(self.classes[base], _seen | {info.name}))
            else:
                depths.append(1)  # external base (Exception, BaseModel, ...): one level
        return 1 + max(depths)

    def all_public_methods(self, info: ClassInfo) -> set[str]:
        names = {m for m in info.methods if not m.startswith("_")}
        for ancestor in self.ancestors(info):
            names |= {m for m in ancestor.methods if not m.startswith("_")}
        return names

    # ---- metrics -----------------------------------------------------------------------------
    def wmc(self, info: ClassInfo) -> int:
        return sum(_complexity(m) for m in info.methods.values())

    def _used_names(self, info: ClassInfo) -> set[str]:
        used: set[str] = set()
        for node in ast.walk(info.node):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                used.update(
                    part for part in node.value.replace("[", " ").split() if part.isidentifier()
                )
        return used

    def coupled_with(self, info: ClassInfo) -> set[str]:
        known = self.imports[info.path] | {n for n in self.classes if n != info.name}
        bases = set(info.bases)
        return (self._used_names(info) & known) - IGNORED_NAMES - {info.name} - bases | (
            bases & set(self.classes)
        )

    def cbo(self, info: ClassInfo) -> int:
        return len(self.coupled_with(info))

    def rfc(self, info: ClassInfo) -> int:
        callees: set[str] = set()
        for method in info.methods.values():
            for node in ast.walk(method):
                if isinstance(node, ast.Call):
                    callees.add(ast.unparse(node.func))
        return len(info.methods) + len(
            callees - set(info.methods) - {f"self.{m}" for m in info.methods}
        )

    def _self_attrs(self, fn: ast.AST) -> set[str]:
        return {
            n.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        }

    @staticmethod
    def _propagate(usage: dict[str, set[str]], calls: dict[str, set[str]]) -> None:
        for _ in range(len(usage)):  # propagate through (possibly nested) self-calls
            for name, callees in calls.items():
                for callee in callees:
                    usage[name] |= usage[callee]

    def _direct_usage(self, info: ClassInfo) -> tuple[dict, dict]:
        names = set(info.methods)
        direct = {n: self._self_attrs(fn) for n, fn in info.methods.items()}
        usage = {n: attrs - names for n, attrs in direct.items()}
        calls = {n: attrs & names for n, attrs in direct.items()}
        return usage, calls

    def _cohesion_methods(self, info: ClassInfo) -> dict[str, set[str]]:
        """Attributes touched by each method; calling ``self.other()`` inherits other's attrs."""
        usage, calls = self._direct_usage(info)
        self._propagate(usage, calls)
        public = [n for n in info.methods if not n.startswith("__")]
        return {n: usage[n] | {f"(){c}" for c in calls[n]} for n in public}

    @staticmethod
    def _linked(usage: dict[str, set[str]], a: str, b: str) -> bool:
        shared = {x for x in usage[a] & usage[b] if not x.startswith("()")}
        return bool(shared) or "()" + b in usage[a] or "()" + a in usage[b]

    def lcom4(self, info: ClassInfo) -> int:
        usage = self._cohesion_methods(info)
        parent = {m: m for m in usage}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        names = list(usage)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                if self._linked(usage, a, b):
                    parent[find(a)] = find(b)
        return len({find(m) for m in names})

    def lcom_hs(self, info: ClassInfo) -> float:
        usage = self._cohesion_methods(info)
        attrs = {a for used in usage.values() for a in used if not a.startswith("()")}
        m, a = len(usage), len(attrs)
        if m <= 1 or a == 0:
            return 0.0
        mean_access = sum(sum(1 for used in usage.values() if attr in used) for attr in attrs) / a
        return round((mean_access - m) / (1 - m), 2) + 0.0

    def lorenz_kidd(self, info: ClassInfo) -> tuple[int, int, int]:
        inherited = set()
        for ancestor in self.ancestors(info):
            inherited |= {m for m in ancestor.methods if not m.startswith("__")}
        own = {m for m in info.methods if not m.startswith("__")}
        return len(own - inherited), len(own & inherited), len(self.all_public_methods(info))

    def measures(self, info: ClassInfo) -> dict[str, float]:
        nma, nmo, pim = self.lorenz_kidd(info)
        return {
            "class_complexity": self.wmc(info),
            "coupling_between_objects": self.cbo(info),
            "lcom4": self.lcom4(info),
            "lcom": self.lcom_hs(info),
            "rfc": self.rfc(info),
            "dit": self.dit(info),
            "public_interface_size": pim,
            "overridden_methods": nmo,
            "new_methods": nma,
        }


def _module_unit(path: Path) -> ClassInfo:
    """Treat a module of free functions (e.g. services/rental_service.py) as one pseudo-class."""
    tree = _parse(path)
    node = ast.ClassDef(name=f"<module {path.stem}>", bases=[], keywords=[], decorator_list=[])
    node.body = [s for s in tree.body if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef)]
    return _make_class(node, path)


def component_measures(path: Path) -> dict:
    """SonarQube ``api/measures/component``-shaped JSON for one file."""
    project = Project(path)
    units = [c for c in project.classes.values() if c.path == path]
    module = _module_unit(path)
    if module.methods:  # free functions form a pseudo-class of their own
        project.classes[module.name] = module
        units.append(module)
    totals: dict[str, float] = {}
    for unit in units:
        for key, value in project.measures(unit).items():
            totals[key] = max(totals.get(key, 0), value)
    totals["class_complexity"] = sum(project.wmc(u) for u in units)
    return {
        "component": {
            "key": f"fleet-management:{path.as_posix()}",
            "path": path.as_posix(),
            "qualifier": "FIL",
            "measures": [{"metric": k, "value": str(v)} for k, v in totals.items()],
            "classes": [u.name for u in units],
        },
        "source": "scripts/ck_metrics.py (AST analyser; values are max over classes, WMC is a sum)",
    }


def _coupled_pairs(project: Project) -> int:
    return sum(
        1
        for c in project.classes.values()
        for other in project.coupled_with(c)
        if other in project.classes and other not in c.bases
    )


def _pct(part: int, total: int, digits: int = 1) -> float:
    return round(100 * part / total, digits) if total else 0.0


def mood(root: Path) -> dict:
    project = Project(root)
    classes = list(project.classes.values())
    methods = [m for c in classes for m in c.methods if not m.startswith("__")]
    attrs = [a for c in classes for a in _all_attrs(project, c)]
    hidden_m = sum(m.startswith("_") for m in methods)
    hidden_a = sum(a.startswith("_") for a in attrs)
    n, pairs = len(classes), _coupled_pairs(project)
    return {
        "classes": n,
        "MHF": _pct(hidden_m, len(methods)),
        "AHF": _pct(hidden_a, len(attrs)),
        "COF": _pct(pairs, n * (n - 1), 2),
        "coupled_pairs": pairs,
        "hidden_methods": f"{hidden_m}/{len(methods)}",
        "hidden_attributes": f"{hidden_a}/{len(attrs)}",
    }


def _all_attrs(project: Project, info: ClassInfo) -> set[str]:
    attrs = set(info.class_attrs)
    for method in info.methods.values():
        for node in ast.walk(method):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    attrs.add(node.attr)
    return attrs


def table(root: Path) -> str:
    project = Project(root)
    cols = ["class_complexity", "coupling_between_objects", "lcom4", "lcom", "rfc", "dit",
            "public_interface_size", "overridden_methods"]  # fmt: skip
    head = ["class", "WMC", "CBO", "LCOM4", "LCOM", "RFC", "DIT", "PIM", "NMO"]
    rows = [head]
    for info in sorted(project.classes.values(), key=lambda c: (str(c.path), c.name)):
        values = project.measures(info)
        rows.append([info.name] + [str(values[c]) for c in cols])
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(r, widths, strict=False)) for r in rows
    )


def _matrix_rows(used: list[str], refs: dict[str, set[str]]) -> list[str]:
    short = {n: f"c{i}" for i, n in enumerate(used)}
    lines = ["| row uses col | " + " | ".join(short[n] for n in used) + " | out |"]
    lines.append("|---" * (len(used) + 2) + "|")
    for n in used:
        cells = ["X" if m in refs[n] else "" for m in used]
        lines.append(f"| {short[n]} {n} | " + " | ".join(cells) + f" | {len(refs[n])} |")
    incoming = [str(sum(1 for r in refs.values() if m in r)) for m in used]
    lines.append("| in | " + " | ".join(incoming) + " | |")
    return lines


def matrix(root: Path) -> str:
    """Coupling matrix: row class refers to column class (X), plus a Mermaid dependency graph."""
    project = Project(root)
    names = sorted(project.classes)
    refs = {n: project.coupled_with(project.classes[n]) & set(names) for n in names}
    used = [n for n in names if refs[n] or any(n in r for r in refs.values())]
    lines = _matrix_rows(used, refs) + ["", "```mermaid", "graph LR"]
    lines += [f"  {n} --> {m}" for n in used for m in sorted(refs[n])]
    lines.append("```")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in {"component", "class", "mood", "table", "matrix"}:
        print(__doc__)
        return 2
    path = Path(argv[2])
    if argv[1] == "component":
        print(json.dumps(component_measures(path), indent=2))
    elif argv[1] == "class":
        project = Project(path)
        print(json.dumps({argv[3]: project.measures(project.classes[argv[3]])}, indent=2))
    elif argv[1] == "mood":
        print(json.dumps(mood(path), indent=2))
    elif argv[1] == "matrix":
        print(matrix(path))
    else:
        print(table(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
