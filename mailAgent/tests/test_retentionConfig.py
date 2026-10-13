"""Retention configuration validation tests."""

from pathlib import Path

import pytest

from mailAgent.configuration import configValidate


def configBuild(months=None):
    general = {}
    if months is not None:
        general["imapRetentionMonths"] = months
    return {
        "general": general,
        "mailboxes": [
            {
                "id": "andy",
                "name": "Andy",
                "host": "mail.example",
                "username": "andy",
                "credentialId": "andy",
                "role": "personal",
                "localArchive": "myMail",
            }
        ],
    }


def testRetentionMonthsDefaultsToTwelve(tmp_path: Path):
    config = configValidate(configBuild(), tmp_path)
    assert config["general"]["imapRetentionMonths"] == 12


def testRetentionMonthsAcceptConfiguredValue(tmp_path: Path):
    config = configValidate(configBuild(18), tmp_path)
    assert config["general"]["imapRetentionMonths"] == 18


@pytest.mark.parametrize("value", [0, -1, 121, 12.0, "12", True])
def testRetentionMonthsRejectInvalidValues(tmp_path: Path, value):
    with pytest.raises(ValueError, match="imapRetentionMonths"):
        configValidate(configBuild(value), tmp_path)
