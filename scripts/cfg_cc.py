"""Computes McCabe's CC = E - V + 2 from Mermaid control-flow graphs written in a Markdown file.

A graph is a fenced ```mermaid block whose first line is a ``%% cfg: <name>`` comment. Edges are
written one per line as ``A --> B``, ``A -->|label| B`` or ``A -.-> B`` (dashed edges are the
planned extension and are counted too); nodes are the identifiers that occur on edges.

    python scripts/cfg_cc.py docs/lab6-complexity-audit/REPORT.md
"""

import re
import sys
from pathlib import Path

BLOCK = re.compile(r"```mermaid\n%% cfg: (?P<name>[\w-]+)\n(?P<body>.*?)```", re.DOTALL)
EDGE = re.compile(r"^\s*(?P<src>\w+)\s*(?:-->|-\.->)(?:\|[^|]*\|)?\s*(?P<dst>\w+)\s*$")


def parse_edges(body: str) -> list[tuple[str, str]]:
    matches = (EDGE.match(line) for line in body.splitlines())
    return [(m["src"], m["dst"]) for m in matches if m]


def cyclomatic_complexity(edges: list[tuple[str, str]]) -> tuple[int, int, int]:
    nodes = {node for edge in edges for node in edge}
    return len(edges), len(nodes), len(edges) - len(nodes) + 2


def main(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8")
    for block in BLOCK.finditer(text):
        e, v, cc = cyclomatic_complexity(parse_edges(block["body"]))
        print(f"{block['name']}: E={e} V={v} CC=E-V+2={cc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
