"""Guidance UX remains explicit, read-only and easy to understand."""

from mailAgent.auditUi import _planActionText
from mailAgent.interest import interestSuggest
from mailAgent.migrationPlanning import _roleBoundary


def testRoleBoundaryDescribesEveryMailboxRole():
    assert _roleBoundary(dict(id="andy", role="personal")) == {
        "mailbox": "andy",
        "role": "personal",
        "reason": "Canonical local archive; live-year mail remains in personal IMAP",
    }
    assert _roleBoundary(
        dict(id="old", role="legacy", migrationTarget="andy")
    )["reason"] == "Migrate into personal mailbox andy"
    assert "shared server taxonomy" in _roleBoundary(
        dict(id="hwfc", role="shared")
    )["reason"]
    assert "no personal archive migration" in _roleBoundary(
        dict(id="support", role="support")
    )["reason"]


def testInboxDigestSuggestionsUseTransparentSubjectSignals():
    assert interestSuggest(
        "orders@example.com", ["Your order has been dispatched"]
    ) == (True, "dispatch")
    assert interestSuggest(
        "hospital@example.com", ["Appointment reminder"]
    ) == (True, "appointment")
    assert interestSuggest("news@example.com", ["Weekly newsletter"]) == (False, "")


def testPlanActionTextPointsUserAtReviewQueue():
    plan = dict(reviewQueue=[{}, {}], proposals=[])
    assert _planActionText(plan) == (
        "⚠ ACTION NEEDED: 2 items need decisions — open Review Queue."
    )


def testPlanActionTextHighlightsMissingMirrorsAfterReview():
    plan = dict(
        reviewQueue=[],
        proposals=[dict(requiresFolderCreation=True), dict(requiresFolderCreation=False)],
    )
    assert "review Proposed Moves" in _planActionText(plan)


def testPlanActionTextCanSayNothingIsRequired():
    assert _planActionText(dict(reviewQueue=[], proposals=[])).startswith("✓")
