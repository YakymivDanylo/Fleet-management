import importlib.util
import textwrap
from pathlib import Path

import pytest

GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "complexity_gate.py"
spec = importlib.util.spec_from_file_location("complexity_gate", GATE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _block(name, complexity, type_="function", **extra):
    return {
        "type": type_,
        "name": name,
        "lineno": 1,
        "complexity": complexity,
        "rank": "C",
        **extra,
    }


def test_function_over_limit_is_reported():
    problems = gate.find_problems({"a.py": [_block("messy", 11)]})
    assert problems == ["a.py:1 messy() has CC=11 (rank C), limit is 10"]


def test_function_at_limit_is_allowed():
    assert gate.find_problems({"a.py": [_block("ok", 10)]}) == []


def test_methods_and_closures_are_checked_but_class_total_is_not():
    cls = _block(
        "Big",
        30,
        type_="class",
        methods=[_block("fine", 3, type_="method"), _block("bad", 12, type_="method")],
    )
    outer = _block("outer", 2, closures=[_block("inner", 15)])
    problems = gate.find_problems({"a.py": [cls, outer]})
    assert [p.split()[1] for p in problems] == ["bad()", "inner()"]


def test_unparsable_file_blocks_the_commit():
    problems = gate.find_problems({"broken.py": {"error": "invalid syntax"}})
    assert problems == ["broken.py: cannot analyse (invalid syntax)"]


MESSY = textwrap.dedent(
    """
    def f(a):
        if a == 1:
            return 1
    """
    + "".join(f"    if a == {n}:\n        return {n}\n" for n in range(2, 13))
)


def test_main_returns_one_for_messy_file_and_zero_for_clean_file(tmp_path, capsys):
    messy = tmp_path / "messy.py"
    messy.write_text(MESSY)
    clean = tmp_path / "clean.py"
    clean.write_text("def g(a):\n    return a\n")

    assert gate.main([str(messy)]) == 1
    assert "COMPLEXITY GATE FAILED" in capsys.readouterr().out
    assert gate.main([str(clean)]) == 0
    assert gate.main([]) == 0


def test_radon_failure_exits_with_message(monkeypatch):
    class Failed:
        returncode = 2
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: Failed())
    with pytest.raises(SystemExit):
        gate.run_radon(["x.py"])
