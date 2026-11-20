"""Lab 10 (QE): Documentation Decay audit — currency metrics of every knowledge artifact from Git.

    python scripts/doc_audit.py --today 2026-11-14 [--json out.json] [--strict]

Per document (registry ``DOCS`` below) the script runs plain Git CLI commands and prints them:

* Last Updated Age  — ``git log -1 --format=%cs -- <doc>``; > 90 days suspicious, > 180 stale.
* Code-Doc drift    — ``git log --oneline <doc_last_commit>..HEAD -- <component paths>``: commits to
  the code the document describes made after the document was last touched (> 20 = structural
  drift). The total ``git log --oneline -- <component>`` is shown for the Code-Doc Change Ratio.
* Broken links      — relative Markdown links ``[x](path)`` that do not resolve in the work tree.
* Access evidence   — inbound references (tracked files that mention the doc file name) and commit
  messages of the last 30 days that mention it; zero of both marks a Dead Documentation candidate.
* Contract drift    — for documents that list the HTTP API, every FastAPI route found in
  ``src/fleet_management/api`` must be mentioned in the document (``--routes``).

``--strict`` exits 1 when any document is FAIL (stale, drifted, broken links or missing routes).
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUSPICIOUS_DAYS, STALE_DAYS, DRIFT_LIMIT = 90, 180, 20

# doc path -> (code paths it describes, check API routes?)
DOCS: dict[str, tuple[list[str], bool]] = {
    "README.md": (["src", "docker-compose.yml", "charts", "Dockerfile"], False),
    # Lab 11: the passport lives in the MkDocs knowledge base; SDD keeps the full route inventory.
    "docs/architecture/sdd.md": (["src/fleet_management"], True),
    "docs/architecture/isd.md": (
        ["docker-compose.yml", "charts", ".github/workflows", "nginx"],
        False,
    ),
    "docs/api/openapi.yaml": (
        ["src/fleet_management/api", "src/fleet_management/schemas.py"],
        False,
    ),
    "k8s/README.md": (["k8s"], False),
    "charts/fleet-management/README.md": (["charts/fleet-management"], False),
    "CHANGELOG.md": (["src", "charts"], False),
    ".env.example": (["src/fleet_management/config.py", "docker-compose.yml"], False),
}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")
PREFIX_RE = re.compile(r'(\w+)\s*=\s*APIRouter\(\s*prefix="([^"]*)"')


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@dataclass
class DocMetrics:
    doc: str
    exists: bool
    last_updated: str | None = None
    age_days: int | None = None
    doc_commits: int = 0
    code_commits_total: int = 0
    code_commits_since_doc: int = 0
    broken_links: list[str] = field(default_factory=list)
    inbound_refs: int = 0
    mentions_30d: int = 0
    missing_routes: list[str] = field(default_factory=list)
    verdict: str = "PASS"
    reasons: list[str] = field(default_factory=list)


def api_routes() -> list[str]:
    routes = []
    for path in sorted((ROOT / "src/fleet_management/api").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        prefixes = dict(PREFIX_RE.findall(text))
        current = next(iter(prefixes.values()), "")
        for line in text.splitlines():
            if m := re.search(r'@(\w+)\.(get|post|put|patch|delete)\(\s*"([^"]*)"', line):
                current = prefixes.get(m.group(1), current)
                routes.append(f"{m.group(2).upper()} {current}{m.group(3)}")
    return routes


def _count(out: str) -> int:
    return len(out.splitlines()) if out else 0


def _git_currency(m: DocMetrics, code: list[str], today: date) -> None:
    m.code_commits_total = _count(git("log", "--oneline", "--", *code))
    last = git("log", "-1", "--format=%H %cs", "--", m.doc)
    if not last:
        m.reasons.append("not committed yet")
        return
    sha, day = last.split()
    m.last_updated, m.age_days = day, (today - date.fromisoformat(day)).days
    m.doc_commits = _count(git("log", "--oneline", "--", m.doc))
    m.code_commits_since_doc = _count(git("log", "--oneline", f"{sha}..HEAD", "--", *code))


def _broken_links(doc: str, text: str) -> list[str]:
    base = (ROOT / doc).parent
    local = [t for t in LINK_RE.findall(text) if "://" not in t and not t.startswith("mailto:")]
    return [t for t in local if not base.joinpath(t).resolve().exists()]


def _access_evidence(m: DocMetrics, today: date, tracked: list[str]) -> None:
    since = (today - timedelta(days=30)).isoformat()
    name = Path(m.doc).name
    m.mentions_30d = _count(git("log", "--oneline", "-i", f"--since={since}", f"--grep={name}"))
    m.inbound_refs = sum(1 for f in tracked if f != m.doc and name in _safe_read(ROOT / f))


def audit_doc(
    doc: str,
    code: list[str],
    check_routes: bool,
    today: date,
    routes: list[str],
    tracked: list[str],
) -> DocMetrics:
    m = DocMetrics(doc, (ROOT / doc).exists())
    if not m.exists:
        m.verdict, m.reasons = "FAIL", ["document missing"]
        return m
    _git_currency(m, code, today)
    text = (ROOT / doc).read_text(encoding="utf-8")
    m.broken_links = _broken_links(doc, text)
    _access_evidence(m, today, tracked)
    if check_routes:
        m.missing_routes = [r for r in routes if r.split(" ", 1)[1] not in text]
    _judge(m)
    return m


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.stat().st_size < 400_000 else ""
    except (OSError, UnicodeDecodeError):
        return ""


def _age_reason(age: int | None) -> str | None:
    if age is None or age <= SUSPICIOUS_DAYS:
        return None
    if age > STALE_DAYS:
        return f"stale: {age} d > {STALE_DAYS}"
    return f"suspicious: {age} d > {SUSPICIOUS_DAYS}"


SOFT_REASONS = ("suspicious", "no consumer", "not committed")


# (violated?, message) rules; a rule whose message starts with a SOFT_REASONS prefix only warns.
RULES = (
    (
        lambda m: m.code_commits_since_doc > DRIFT_LIMIT,
        lambda m: f"drift: {m.code_commits_since_doc} code commits without doc update",
    ),
    (lambda m: bool(m.broken_links), lambda m: f"{len(m.broken_links)} broken links"),
    (
        lambda m: bool(m.missing_routes),
        lambda m: f"{len(m.missing_routes)} API routes not documented",
    ),
    (
        lambda m: m.inbound_refs == 0 and m.mentions_30d == 0,
        lambda m: "no consumer evidence (dead documentation candidate)",
    ),
)
VERDICTS = {
    (True, True): "FAIL",
    (True, False): "FAIL",
    (False, True): "WARN",
    (False, False): "PASS",
}


def _judge(m: DocMetrics) -> None:
    age = _age_reason(m.age_days)
    m.reasons.extend([age] if age else [])
    m.reasons.extend(message(m) for violated, message in RULES if violated(m))
    hard = any(not r.startswith(SOFT_REASONS) for r in m.reasons)
    m.verdict = VERDICTS[(hard, bool(m.reasons))]


def _row(m: DocMetrics) -> str:
    age = "—" if m.age_days is None else m.age_days
    return (
        f"| `{m.doc}` | {m.last_updated or '—'} | {age} | {m.doc_commits}"
        f" | {m.code_commits_total} / {m.code_commits_since_doc} | {len(m.broken_links)}"
        f" | {m.inbound_refs} | {m.mentions_30d} | {len(m.missing_routes)} | {m.verdict} |"
    )


def _details(m: DocMetrics) -> list[str]:
    lines = [f"  - {m.doc}: {r}" for r in m.reasons]
    lines += [f"      broken link -> {link}" for link in m.broken_links]
    lines += [f"      undocumented route -> {route}" for route in m.missing_routes]
    return lines


def report(results: list[DocMetrics], today: date, routes: int) -> list[str]:
    head = git("rev-parse", "--short", "HEAD")
    lines = [
        f"today={today} head={head} api_routes={routes}",
        "| Document | Last updated | Age, d | Doc commits | Code commits (total / since doc)"
        " | Broken links | Inbound refs | Mentions 30d | Missing routes | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_row(m) for m in results]
    for m in results:
        lines += _details(m)
    failed = [m.doc for m in results if m.verdict == "FAIL"]
    lines.append(f"documentation currency: {'FAIL ' + str(failed) if failed else 'PASS'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--json", type=Path)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--only", nargs="*", help="audit only these documents")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    today = date.fromisoformat(a.today)
    routes, tracked = api_routes(), git("ls-files").splitlines()
    docs = {d: v for d, v in DOCS.items() if not a.only or d in a.only}
    results = [audit_doc(d, code, chk, today, routes, tracked) for d, (code, chk) in docs.items()]
    print("\n".join(report(results, today, len(routes))))
    if a.json:
        payload = json.dumps([asdict(m) for m in results], ensure_ascii=False, indent=2)
        a.json.write_text(payload, encoding="utf-8")
    failed = any(m.verdict == "FAIL" for m in results)
    return 1 if a.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
