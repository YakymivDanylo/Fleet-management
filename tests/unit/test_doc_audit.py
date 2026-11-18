"""Lab 10: Documentation Decay audit rules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import doc_audit as da  # noqa: E402


def _judged(**kw) -> da.DocMetrics:
    m = da.DocMetrics("doc.md", True, inbound_refs=1, **kw)
    da._judge(m)
    return m


def test_fresh_document_passes():
    assert _judged(age_days=10, code_commits_since_doc=3).verdict == "PASS"


def test_age_thresholds():
    assert _judged(age_days=91).verdict == "WARN"
    assert _judged(age_days=181).verdict == "FAIL"


def test_structural_drift_over_twenty_commits_fails():
    assert _judged(age_days=1, code_commits_since_doc=20).verdict == "PASS"
    assert _judged(age_days=1, code_commits_since_doc=21).verdict == "FAIL"


def test_broken_links_and_missing_routes_fail():
    assert _judged(broken_links=["docs/x.md"]).verdict == "FAIL"
    assert _judged(missing_routes=["GET /x"]).verdict == "FAIL"


def test_no_consumer_is_dead_documentation_warning():
    m = da.DocMetrics("doc.md", True, age_days=1)
    da._judge(m)
    assert m.verdict == "WARN" and "dead documentation" in m.reasons[0]


def test_every_api_route_is_discovered():
    routes = da.api_routes()
    assert "GET /vehicles/{vehicle_id}/state" in routes
    assert "POST /api/marketing/dispatch" in routes
    assert len(routes) == len(set(routes))
