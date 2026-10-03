"""Human-readable presentation for migration planning."""

from collections import Counter


def planSummaryLines(plan: dict) -> list[str]:
    """Build concise user-facing lines from a structured migration plan."""
    summary = plan.get("summary", {})
    proposals = plan.get("proposals", [])
    reviews = plan.get("reviewQueue", [])
    mappings = plan.get("mappings", [])

    lines = [
        "Planning only - no mail has been changed.",
        "",
        "Plan summary",
        f'  Messages scanned: {summary.get("messagesScanned", 0)}',
        f'  Proposed actions: {summary.get("proposals", len(proposals))}',
        f'  Messages/folders needing review: {summary.get("reviewItems", len(reviews))}',
        (
            "  System-folder messages excluded: "
            f'{summary.get("systemFolderMessagesExcluded", 0)}'
        ),
    ]

    invalidDates = summary.get("messagesWithInvalidDates", 0)
    if invalidDates:
        lines.append(f"  Messages with invalid/unknown dates: {invalidDates}")

    mailboxIds = []
    for item in mappings + reviews:
        mailbox = item.get("mailbox")
        if mailbox and mailbox not in mailboxIds:
            mailboxIds.append(mailbox)
    for proposal in proposals:
        mailbox = proposal.get("source", {}).get("mailbox")
        if mailbox and mailbox not in mailboxIds:
            mailboxIds.append(mailbox)

    if mailboxIds:
        lines.extend(["", "By mailbox"])
    for mailbox in mailboxIds:
        mailboxProposals = [
            proposal
            for proposal in proposals
            if proposal.get("source", {}).get("mailbox") == mailbox
        ]
        mailboxReviews = [review for review in reviews if review.get("mailbox") == mailbox]
        unclassified = sum(
            1
            for review in mailboxReviews
            if review.get("source")
            and review.get("reason") == "No unambiguous canonical archive folder"
        )
        mirrors = sum(
            1
            for mapping in mappings
            if mapping.get("mailbox") == mailbox and mapping.get("mirrorProposed")
        )
        lines.append(f"  {mailbox}")
        lines.append(f"    Proposed actions: {len(mailboxProposals)}")
        lines.append(f"    Review items: {len(mailboxReviews)}")
        if unclassified:
            lines.append(f"    Messages needing classification: {unclassified}")
        if mirrors:
            lines.append(f"    IMAP mirror folders proposed: {mirrors}")

    decisions = []
    for review in reviews:
        policy = review.get("policy")
        if policy == "explicitSentMapping":
            decisions.append(
                (
                    review.get("mailbox"),
                    review.get("folder"),
                    review.get("messageCount"),
                    "choose the canonical archive folder for Sent mail",
                )
            )
        elif policy == "exclude" and review.get("requiresRetentionDecision"):
            decisions.append(
                (
                    review.get("mailbox"),
                    review.get("folder"),
                    review.get("messageCount"),
                    "choose the future retention policy",
                )
            )
    if decisions:
        lines.extend(["", "Decisions needed"])
        for mailbox, folder, count, decision in decisions:
            countText = "unknown count" if count is None else f"{count} messages"
            lines.append(f"  {mailbox}/{folder}: {countText} - {decision}")

    grouped = Counter(
        (review.get("mailbox"), review.get("reason"))
        for review in reviews
        if review.get("source")
    )
    if grouped:
        lines.extend(["", "Message issues"])
        for (mailbox, reason), count in sorted(grouped.items()):
            lines.append(f"  {mailbox}: {count} - {reason}")

    nextSteps = []
    if any(
        reason == "No unambiguous canonical archive folder"
        for _, reason in grouped
    ):
        nextSteps.append(
            "Resolve classification of INBOX/archive messages against the local taxonomy."
        )
    if any(review.get("policy") == "explicitSentMapping" for review in reviews):
        nextSteps.append("Choose canonical archive mappings for Sent mail.")
    if any(
        review.get("policy") == "exclude"
        and review.get("requiresRetentionDecision")
        for review in reviews
    ):
        nextSteps.append(
            "Decide future retention for Trash/Junk/Drafts; they remain excluded for now."
        )
    if any(mapping.get("mirrorProposed") for mapping in mappings):
        nextSteps.append("Review proposed IMAP mirror folders before any are created.")
    if not proposals:
        nextSteps.append(
            "No message moves are currently proposed; resolve the review items first."
        )

    if nextSteps:
        lines.extend(["", "Next actions"])
        lines.extend(f"  - {step}" for step in nextSteps)

    return lines


def planSummaryShow(plan: dict, logger) -> None:
    """Write the concise migration-plan summary through logUtils."""
    for line in planSummaryLines(plan):
        logger.info(line)
