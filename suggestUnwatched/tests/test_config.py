"""Exempt-list config preserves unknown keys and ignores case."""

import json

import pytest

from suggestUnwatched.config import configLoad, configSave, exemptAdd, exemptRemove


def test_missing_file_exempts_nothing(tmp_path) -> None:
    assert configLoad(tmp_path / "missing.json") == []


def test_load_rejects_a_bare_list(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        configLoad(path)


def test_save_preserves_unknown_keys(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"theme": "dark", "exemptShows": ["UFO"]}\n', encoding="utf-8")

    configSave(path, exemptAdd(["UFO"], "thunderbirds"))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["theme"] == "dark"
    assert saved["exemptShows"] == ["UFO", "thunderbirds"]
    assert exemptRemove(saved["exemptShows"], "UFO") == ["thunderbirds"]


def test_add_rejects_a_blank_name() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        exemptAdd([], "  ")
