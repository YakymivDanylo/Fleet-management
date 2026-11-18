"""Lab 9 (QE): retrospective effort of a sub-module from its Git history (git-hours heuristic).

    python scripts/git_effort.py --repo <clone> --rev v3.3.9 --path netbox/users --json out.json

For every author the commit timestamps that touched ``--path`` are sorted; consecutive commits
closer than ``--max-gap`` hours belong to one working session and the gap is counted as effort;
the first commit of every session gets ``--first-commit`` hours (work done before that commit).
Merge commits are skipped (they carry no authored work). Identities of one person (several e-mails,
``Jane Doe`` vs ``janedoe``) are merged by the normalised author name.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AuthorEffort:
    author: str
    commits: int
    sessions: int
    hours: float
    first: str
    last: str


def read_commits(repo: str, rev: str, path: str) -> list[tuple[str, str, int]]:
    out = subprocess.run(
        ["git", "-C", repo, "log", "--no-merges", "--format=%ae%x09%an%x09%at", rev, "--", path],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    commits = []
    for line in out.splitlines():
        email, name, ts = line.split("\t")
        commits.append((email.lower(), name, int(ts)))
    return commits


def estimate(
    commits: list[tuple[str, str, int]], max_gap_h: float, first_commit_h: float
) -> list[AuthorEffort]:
    by_author: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    for _email, name, ts in commits:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        by_author[key].append(ts)
        names.setdefault(key, name)
    result = []
    for key, stamps in by_author.items():
        stamps.sort()
        hours, sessions = first_commit_h, 1
        for prev, cur in zip(stamps, stamps[1:], strict=False):
            gap = (cur - prev) / 3600
            if gap < max_gap_h:
                hours += gap
            else:
                hours += first_commit_h
                sessions += 1
        day = lambda ts: datetime.fromtimestamp(ts, UTC).date().isoformat()  # noqa: E731
        result.append(
            AuthorEffort(
                names[key], len(stamps), sessions, round(hours, 2), day(stamps[0]), day(stamps[-1])
            )
        )
    return sorted(result, key=lambda a: a.hours, reverse=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", required=True)
    p.add_argument("--rev", default="HEAD")
    p.add_argument("--path", required=True)
    p.add_argument("--max-gap", type=float, default=2.0, help="session gap, hours")
    p.add_argument("--first-commit", type=float, default=2.0, help="hours before 1st commit")
    p.add_argument("--json", help="write the full result as JSON")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    authors = estimate(read_commits(a.repo, a.rev, a.path), a.max_gap, a.first_commit)
    total_h = sum(x.hours for x in authors)
    total_c = sum(x.commits for x in authors)
    print(
        f"path={a.path} rev={a.rev} commits={total_c} authors={len(authors)}"
        f" effort={total_h:.2f} h (max_gap={a.max_gap} h, first_commit={a.first_commit} h)"
    )
    print("| Author | Commits | Sessions | Hours | First | Last |\n|---|---|---|---|---|---|")
    for x in authors:
        print(f"| {x.author} | {x.commits} | {x.sessions} | {x.hours} | {x.first} | {x.last} |")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "path": a.path,
                    "rev": a.rev,
                    "commits": total_c,
                    "authors": len(authors),
                    "hours": round(total_h, 2),
                    "by_author": [asdict(x) for x in authors],
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
