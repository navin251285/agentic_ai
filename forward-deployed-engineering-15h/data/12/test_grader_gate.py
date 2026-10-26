"""Gate for the graders (lesson 12). No model is called: it reads the saved verdicts."""
import json
from pathlib import Path

import pytest
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).resolve().parent
GRADERS = {"code": "code_v2.json", "model": "model.json"}


def load(name):
    return json.loads((HERE / name).read_text())


def test_every_case_has_a_verdict_from_each_grader():
    if not (HERE / "person.json").exists():
        pytest.skip("no saved verdicts yet")
    person = load("person.json")
    for name in GRADERS.values():
        assert set(load(name)) == set(person), name


def test_each_automatic_grader_agrees_with_the_person():
    if not (HERE / "person.json").exists():
        pytest.skip("no saved verdicts yet")
    person = load("person.json")
    for grader, name in GRADERS.items():
        got = load(name)
        kappa = cohen_kappa_score([got[c] for c in person], [person[c] for c in person])
        assert kappa >= 0.6, f"{grader} grader kappa {kappa:.2f} is below 0.6: do not run it alone"
