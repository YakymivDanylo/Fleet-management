"""Lab 7: the Hotspots matrix classifies files on the complexity x churn quadrant."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import hotspots  # noqa: E402


@pytest.mark.parametrize(
    ("total_cc", "churn", "category"),
    [
        (30, 9, "Hotspot"),
        (30, 1, "Sleeping"),
        (10, 9, "Active"),
        (10, 1, "Stable"),
        (25, 5, "Hotspot"),  # both thresholds are inclusive
        (24, 4, "Stable"),
    ],
)
def test_classify_quadrants(total_cc, churn, category):
    assert hotspots.classify(total_cc, churn, cc_threshold=25, churn_threshold=5) == category


def test_read_complexity_sums_blocks_and_normalizes_paths(tmp_path):
    report = {
        r".\src\a.py": [{"complexity": 3}, {"complexity": 7}],
        "./src/b.py": [],
    }
    source = tmp_path / "cc.json"
    source.write_text(json.dumps(report), encoding="utf-8")

    assert hotspots.read_complexity(source) == {"src/a.py": (10, 7), "src/b.py": (0, 0)}


def test_build_matrix_ranks_by_complexity_times_churn():
    complexity = {"a.py": (30, 4), "b.py": (10, 2), "c.py": (40, 9)}
    churn = {"a.py": 8, "b.py": 9}

    rows = hotspots.build_matrix(complexity, churn, cc_threshold=25, churn_threshold=5)

    assert [(r.file, r.category) for r in rows] == [
        ("a.py", "Hotspot"),
        ("b.py", "Active"),
        ("c.py", "Sleeping"),  # never touched: churn defaults to 0
    ]


def test_read_churn_counts_commits_per_file_from_git_log(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    for round_no in range(3):
        (tmp_path / "hot.py").write_text(f"x = {round_no}\n")
        git("add", ".")
        git("commit", "-q", "-m", f"edit {round_no}")
    (tmp_path / "cold.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "add cold")
    monkeypatch.chdir(tmp_path)

    assert hotspots.read_churn("90 days ago") == {"hot.py": 3, "cold.py": 1}
