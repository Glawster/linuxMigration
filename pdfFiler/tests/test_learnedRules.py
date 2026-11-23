"""Learned numbers (criterion 14) and rules (criterion 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import AVIVA_ISA_LINES, AVIVA_TAX_LINES, MBNA_RENEWAL_LINES

from pdfFiler.learned import learnedLoad, learnedNumbersFind, learnedRecord
from pdfFiler.rules import ruleFind, rulesLoad

## learned


def test_learnedNumbersFind() -> None:
    # The MBNA policy number sits lines away from its label but appears twice.
    assert learnedNumbersFind("\n".join(MBNA_RENEWAL_LINES)) == {"MBNAUKM4HAP100000001"}
    # The FCA firm reference is on every Aviva letter and is never learned.
    assert "231530" not in learnedNumbersFind("\n".join(AVIVA_ISA_LINES))
    assert learnedNumbersFind("Account number: 12345678\nSort code 12-34-56") == {"12345678"}
    assert learnedNumbersFind("\n".join(AVIVA_TAX_LINES)) == set()


def test_learnedRecordSavesAndKeepsOtherKeys(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "learned.json"
    path.write_text(json.dumps({"note": "keep me"}))

    # Act
    added, conflicting = learnedRecord(path, {"MBNAUKM4HAP100000001"}, Path("Insurance/MBNA"))

    # Assert
    assert added == ["MBNAUKM4HAP100000001"] and conflicting == []
    raw = json.loads(path.read_text())
    assert raw["note"] == "keep me"
    assert learnedLoad(path).identifiers == {"MBNAUKM4HAP100000001": Path("Insurance/MBNA")}


def test_learnedRecordNeverOverwritesAnotherFolder(tmp_path: Path) -> None:
    path = tmp_path / "learned.json"
    learnedRecord(path, {"ABC1234567"}, Path("Insurance/MBNA"))

    added, conflicting = learnedRecord(path, {"ABC1234567"}, Path("Finance/MBNA"))
    learnedRecord(path, {"ABC1234567"}, Path("Finance/MBNA"))

    learned = learnedLoad(path)
    assert added == [] and conflicting == ["ABC1234567"]
    assert learned.identifiers["ABC1234567"] == Path("Insurance/MBNA")
    assert learned.conflicts == [
        {"identifier": "ABC1234567", "folders": ["Insurance/MBNA", "Finance/MBNA"]}
    ]


## rules


def _config(tmp_path: Path, rules: list) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"rules": rules, "other": 1}))
    return path


def test_exampleConfigLoads() -> None:
    example = Path(__file__).resolve().parents[1] / "config.example.json"
    rules = rulesLoad(example)
    assert [rule.name for rule in rules] == ["Direct Payments bank statement"]
    assert rules[0].yearSubfolder and rules[0].date == "standaloneLine"


def test_ruleMatchesIgnoringCaseAndSpacing(tmp_path: Path) -> None:
    rules = rulesLoad(
        _config(
            tmp_path,
            [
                {
                    "name": "r",
                    "match": ["Account  number: 1", "Bank"],
                    "folder": "A",
                    "label": "L",
                    "type": "T",
                }
            ],
        )
    )
    assert ruleFind(rules, "danske bank\naccount number:   1") is rules[0]
    assert ruleFind(rules, "account number: 1") is None


def test_missingConfigHasNoRules(tmp_path: Path) -> None:
    assert rulesLoad(tmp_path / "absent.json") == []


@pytest.mark.parametrize(
    "rule, problem",
    [
        ({"name": "r", "folder": "A", "label": "L", "type": "T"}, "needs 'match'"),
        ({"name": "r", "match": [], "folder": "A", "label": "L", "type": "T"}, "'match'"),
        ({"name": "r", "match": "x", "folder": "/abs", "label": "L", "type": "T"}, "relative"),
        ({"name": "r", "match": "x", "folder": "../up", "label": "L", "type": "T"}, "relative"),
        (
            {"name": "r", "match": "x", "folder": "A", "label": "L", "type": "T", "date": "x"},
            "'date'",
        ),
        (
            {
                "name": "r",
                "match": "x",
                "folder": "A",
                "label": "L",
                "type": "T",
                "fileName": "x.txt",
            },
            "'fileName'",
        ),
    ],
)
def test_badRulesAreRefused(tmp_path: Path, rule: dict, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        rulesLoad(_config(tmp_path, [rule]))
