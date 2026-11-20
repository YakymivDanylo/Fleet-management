"""Lab 11: review_date audit of the documentation passports."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import docs_review_audit as dra  # noqa: E402

TODAY = date(2026, 11, 20)


def write(docs: Path, name: str, meta: str, body: str = "# Page\n") -> None:
    path = docs / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{meta}\n---\n\n{body}", encoding="utf-8")


def run(docs: Path) -> tuple[list[str], bool]:
    return dra.report(dra.audit(docs), TODAY)


def test_fresh_published_page_passes(tmp_path):
    write(tmp_path, "a.md", "owner: '@x'\nstatus: published\nreview_date: 2027-01-01")
    lines, failed = run(tmp_path)
    assert not failed
    assert lines[-1] == "review audit: PASS"


def test_overdue_live_page_fails_and_is_listed(tmp_path):
    write(tmp_path, "ops/a.md", "owner: '@x'\nstatus: published\nreview_date: 2026-11-01")
    lines, failed = run(tmp_path)
    assert failed
    assert any("`ops/a.md`" in line and "| 19 |" in line for line in lines)


def test_review_due_today_is_not_overdue(tmp_path):
    write(tmp_path, "a.md", "owner: '@x'\nstatus: published\nreview_date: 2026-11-20")
    assert not run(tmp_path)[1]


def test_overdue_deprecated_page_is_tolerated_but_listed(tmp_path):
    write(tmp_path, "new.md", "owner: '@x'\nstatus: published\nreview_date: 2027-01-01")
    meta = "owner: '@x'\nstatus: deprecated\nreview_date: 2026-01-01\nsuperseded_by: new.md"
    write(tmp_path, "old.md", meta)
    lines, failed = run(tmp_path)
    assert not failed
    assert "- `old.md` -> `new.md`" in lines


def test_deprecated_page_must_point_to_existing_replacement(tmp_path):
    meta = "owner: '@x'\nstatus: deprecated\nreview_date: 2027-01-01\nsuperseded_by: gone.md"
    write(tmp_path, "old.md", meta)
    lines, failed = run(tmp_path)
    assert failed
    assert any("missing page: gone.md" in line for line in lines)


def test_missing_passport_and_bad_values_are_invalid(tmp_path):
    (tmp_path / "bare.md").write_text("# No front matter\n", encoding="utf-8")
    write(tmp_path, "bad.md", "owner: '@x'\nstatus: final\nreview_date: someday")
    pages = {p.path: p for p in dra.audit(tmp_path)}
    assert pages["bare.md"].problems == [
        "missing 'owner'",
        "missing 'status'",
        "missing 'review_date'",
    ]
    assert "unknown status 'final'" in pages["bad.md"].problems
    assert any("not a date" in problem for problem in pages["bad.md"].problems)


def test_strict_exit_code(tmp_path):
    write(tmp_path, "a.md", "owner: '@x'\nstatus: draft\nreview_date: 2026-01-01")
    argv = ["--docs", str(tmp_path), "--today", "2026-11-20"]
    assert dra.main(argv) == 0
    assert dra.main([*argv, "--strict"]) == 1


def test_real_knowledge_base_has_valid_passports():
    pages = dra.audit(dra.ROOT / "docs")
    assert pages, "docs/ must not be empty"
    assert [p.path for p in pages if p.problems] == []
