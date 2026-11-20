"""Lab 11: knowledge graph of docs/ — the same links Obsidian draws, checked for islands.

    python scripts/kb_graph.py [--mermaid out.md] [--strict]

Nodes are Markdown pages under ``docs/``; edges are ``[[wikilinks]]`` (resolved by file stem, like
Obsidian and ``docs_hooks/wikilinks.py``) and relative Markdown links to other pages. The script
prints the connected components; more than one component means an isolated "island" of knowledge.
``--strict`` exits 1 in that case. ``--mermaid`` writes the graph as a Mermaid flowchart.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
WIKILINK_RE = re.compile(r"\[\[([^\]|#\\]+)(?:#[^\]|\\]+)?(?:\\?\|[^\]]+)?\]\]")
MDLINK_RE = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
TAG_RE = re.compile(r"(?:^|\s)#(architecture|api|ops|adr)\b")
FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)


def pages(docs: Path) -> dict[str, Path]:
    return {p.relative_to(docs).as_posix(): p for p in sorted(docs.rglob("*.md"))}


def edges(docs: Path) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    found = pages(docs)
    by_stem: dict[str, list[str]] = defaultdict(list)
    for rel in found:
        by_stem[PurePosixPath(rel).stem.lower()].append(rel)
    graph: dict[str, set[str]] = {rel: set() for rel in found}
    unresolved: dict[str, list[str]] = defaultdict(list)
    for rel, path in found.items():
        text = FENCE_RE.sub("", path.read_text(encoding="utf-8"))
        for name in WIKILINK_RE.findall(text):
            targets = by_stem.get(name.strip().lower(), [])
            if len(targets) == 1:
                graph[rel].add(targets[0])
            else:
                unresolved[rel].append(f"[[{name}]]")
        for link in MDLINK_RE.findall(text):
            if "://" in link:
                continue
            target = (PurePosixPath(rel).parent / link).as_posix()
            target = str(PurePosixPath(*_normalize(target.split("/"))))
            if target in graph:
                graph[rel].add(target)
    return graph, unresolved


def _normalize(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if part == "..":
            out.pop()
        elif part not in (".", ""):
            out.append(part)
    return out


def components(graph: dict[str, set[str]]) -> list[list[str]]:
    undirected: dict[str, set[str]] = defaultdict(set)
    for src, dsts in graph.items():
        undirected[src]
        for dst in dsts:
            if dst != src:
                undirected[src].add(dst)
                undirected[dst].add(src)
    seen, result = set(), []
    for start in sorted(undirected):
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            comp.append(node)
            for nxt in undirected[node] - seen:
                seen.add(nxt)
                stack.append(nxt)
        result.append(sorted(comp))
    return sorted(result, key=len, reverse=True)


def mermaid(graph: dict[str, set[str]]) -> str:
    ids = {rel: f"n{i}" for i, rel in enumerate(sorted(graph))}
    lines = ["```mermaid", "flowchart LR"]
    lines += [f'  {ids[rel]}["{PurePosixPath(rel).stem}"]' for rel in sorted(graph)]
    for src in sorted(graph):
        lines += [f"  {ids[src]} --> {ids[dst]}" for dst in sorted(graph[src]) if dst != src]
    lines.append("```")
    return "\n".join(lines)


def degree_lines(graph: dict[str, set[str]]) -> list[str]:
    lines = []
    for rel in sorted(graph):
        out_n = len(graph[rel] - {rel})
        in_n = sum(rel in dsts for src, dsts in graph.items() if src != rel)
        note = "  <- no inbound links" if in_n == 0 else ""
        lines.append(f"  {rel}: out={out_n} in={in_n}{note}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs", type=Path, default=DOCS)
    parser.add_argument("--mermaid", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    graph, unresolved = edges(args.docs)
    comps = components(graph)
    links = sum(len(v - {k}) for k, v in graph.items())
    print(f"pages={len(graph)} links={links} components={len(comps)}")
    for i, comp in enumerate(comps, 1):
        print(f"component {i} ({len(comp)} pages): {', '.join(comp)}")
    print("\n".join(degree_lines(graph)))
    for rel, names in sorted(unresolved.items()):
        print(f"UNRESOLVED in {rel}: {', '.join(names)}")
    if args.mermaid:
        args.mermaid.write_text(mermaid(graph) + "\n", encoding="utf-8")
    connected = len(comps) == 1 and not unresolved
    print(f"knowledge graph: {'CONNECTED' if connected else 'HAS ISLANDS'}")
    return 1 if args.strict and not connected else 0


if __name__ == "__main__":
    raise SystemExit(main())
