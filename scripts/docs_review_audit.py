"""Lab 11: continuous currency audit of the knowledge base — front matter passports vs today.

    python scripts/docs_review_audit.py [--today 2026-11-20] [--strict] [--docs docs]

Every Markdown page under ``docs/`` must carry a passport in its front matter:

* ``owner``       — who keeps the page current;
* ``status``      — ``draft`` | ``in-review`` | ``published`` | ``deprecated``;
* ``review_date`` — the next mandatory review (ISO date).

The script prints every page whose ``review_date`` is in the past. Overdue ``deprecated`` pages are
listed but tolerated (they are history); a deprecated page must name its replacement in
``superseded_by``, and that file must exist. With ``--strict`` the exit code is 1 when a passport is
missing or invalid, or a live (non-deprecated) page is overdue. In GitHub Actions the report is also
written to the job summary.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("draft", "in-review", "published", "deprecated")
REQUIRED = ("owner", "status", "review_date")


@dataclass
class Page:
    path: str
    owner: str | None = None
    status: str | None = None
    review_date: date | None = None
    superseded_by: str | None = None
    problems: list[str] = field(default_factory=list)

    def overdue_days(self, today: date) -> int:
        return (today - self.review_date).days if self.review_date else 0


def front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data = yaml.safe_load(text[4:end]) or {}
    return data if isinstance(data, dict) else {}


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def read_page(path: Path, docs: Path) -> Page:
    meta = front_matter(path.read_text(encoding="utf-8"))
    page = Page(path.relative_to(docs).as_posix())
    page.owner, page.status = meta.get("owner"), meta.get("status")
    page.review_date = _as_date(meta.get("review_date"))
    page.superseded_by = meta.get("superseded_by")
    page.problems += [f"missing '{key}'" for key in REQUIRED if not meta.get(key)]
    if page.status and page.status not in STATUSES:
        page.problems.append(f"unknown status '{page.status}'")
    if meta.get("review_date") and page.review_date is None:
        page.problems.append(f"review_date is not a date: {meta.get('review_date')!r}")
    if page.status == "deprecated":
        if not page.superseded_by:
            page.problems.append("deprecated page without 'superseded_by'")
        elif not (docs / page.superseded_by).is_file():
            page.problems.append(f"superseded_by points to a missing page: {page.superseded_by}")
    return page


def audit(docs: Path) -> list[Page]:
    return [read_page(p, docs) for p in sorted(docs.rglob("*.md"))]


def _action(p: Page) -> str:
    if p.status == "deprecated":
        return f"history, see `{p.superseded_by}`"
    return "review now: update content + review_date, or deprecate"


def _overdue_table(overdue: list[Page], today: date) -> list[str]:
    if not overdue:
        return []
    rows = [
        f"| `{p.path}` | {p.owner} | {p.status} | {p.review_date} "
        f"| {p.overdue_days(today)} | {_action(p)} |"
        for p in overdue
    ]
    header = [
        "| Page | Owner | Status | review_date | Overdue, d | Action |",
        "|---|---|---|---|---|---|",
    ]
    return [*header, *rows, ""]


def _deprecated_list(pages: list[Page]) -> list[str]:
    deprecated = [f"- `{p.path}` -> `{p.superseded_by}`" for p in pages if p.status == "deprecated"]
    if not deprecated:
        return []
    return ["Deprecated pages (kept, redirect to the replacement):", *deprecated, ""]


def _overdue(pages: list[Page], today: date) -> list[Page]:
    late = [p for p in pages if p.review_date and p.review_date < today]
    return sorted(late, key=lambda p: p.review_date)


def _invalid_lines(broken: list[Page]) -> list[str]:
    return [f"- INVALID `{p.path}`: {problem}" for p in broken for problem in p.problems]


def report(pages: list[Page], today: date) -> tuple[list[str], bool]:
    overdue = _overdue(pages, today)
    live_overdue = [p for p in overdue if p.status != "deprecated"]
    broken = [p for p in pages if p.problems]
    lines = [
        f"## Documentation review audit — today {today}",
        "",
        f"Pages: {len(pages)}; overdue: {len(overdue)} "
        f"(live {len(live_overdue)}, deprecated {len(overdue) - len(live_overdue)}); "
        f"invalid passports: {len(broken)}",
        "",
        *_overdue_table(overdue, today),
        *_deprecated_list(pages),
    ]
    lines += _invalid_lines(broken)
    failed = bool(live_overdue or broken)
    lines.append(f"review audit: {'FAIL' if failed else 'PASS'}")
    return lines, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    lines, failed = report(audit(args.docs), date.fromisoformat(args.today))
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(text + "\n")
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
