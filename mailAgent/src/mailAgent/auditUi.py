"""Presentation only for the core audit and planning models."""

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.containers import VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from mailAgent.interest import (
    interestEffective,
    interestLoad,
    interestPersonPolicyGet,
    interestPersonPolicySet,
    interestReasonPolicies,
    interestReasons,
    interestReasonSet,
    interestSenderPolicyGet,
    interestSenderPolicySet,
    interestSuggest,
)
from mailAgent.planSummary import planSummaryLines

## presentation


class _DigestPolicyTable(DataTable):
    """Data table whose left/right arrows edit the selected policy cell."""

    BINDINGS = [
        Binding("left", "policy_left", "", show=False, priority=True),
        Binding("right", "policy_right", "", show=False, priority=True),
    ]

    def action_policy_left(self) -> None:
        handler = getattr(self.app, "_digestPolicyShift", None)
        if handler:
            handler(self, -1)

    def action_policy_right(self) -> None:
        handler = getattr(self.app, "_digestPolicyShift", None)
        if handler:
            handler(self, 1)


def auditAppBuild(snapshot: dict) -> App:
    """Construct the audit app for interactive use or headless validation."""
    try:
        interestData = interestLoad()
        interestIssue = None
    except (OSError, ValueError):
        interestData = {
            "schemaVersion": 1,
            "mailboxes": {},
            "reasonPolicies": {},
            "senderPolicies": {},
            "personPolicies": {},
        }
        interestIssue = "Interesting-sender preferences could not be loaded"
    senderRows = _interestRows(snapshot, interestData)
    filingPlan = snapshot.get("filingPlan") or {}
    filingRows = list(filingPlan.get("rows", []))
    try:
        from mailAgent.filing import filingPath, filingRulesLoad

        filingRulesLoad(filingPath())
        filingIssue = None
    except (OSError, ValueError):
        filingIssue = "Filing rules could not be loaded"

    class MailboxAudit(App):
        TITLE = "Mailbox Audit"
        BINDINGS = [("q", "quit", "Quit")]

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static(
                "Read-only audit · Filing and migration execution disabled",
                id="safety",
                markup=False,
            )
            with TabbedContent():
                with TabPane("Folders", id="folders"):
                    yield from _foldersPane(snapshot)
                yield from _interestPane(
                    senderRows,
                    interestData,
                    interestIssue,
                    filingPlan,
                    filingRows,
                    filingIssue,
                )
                yield from _auditPanes(snapshot)
                yield from _planPane(snapshot.get("migrationPlan"))
            yield Footer()

        def _digestPolicyShift(self, table: DataTable, direction: int) -> None:
            row = table.cursor_coordinate.row
            column = table.cursor_coordinate.column
            if table.id == "digest-reason-table":
                if column != 1 or row < 0 or row >= len(interestReasons()):
                    return
                reason = interestReasons()[row]
                current = interestReasonPolicies(interestData)[reason]
                policy = _policyShift(current, ("out", "manual", "in"), direction)
                updated = interestReasonSet(reason, policy)
                _interestDataReplace(interestData, updated)
                table.update_cell_at(Coordinate(row, 1), Text(policy.title()))
                self.query_one("#digest-reason-status", Static).update(
                    f"{reason.title()} set to {policy.title()}."
                )
                self._digestSenderRowsRefresh()
                return

            if table.id != "interest-table" or row < 0 or row >= len(senderRows):
                return
            entry = senderRows[row]
            if column == 5:
                current = interestSenderPolicyGet(
                    interestData, entry["mailbox"], entry["sender"]
                )
                policy = _policyShift(current, ("out", "auto", "in"), direction)
                updated = interestSenderPolicySet(
                    entry["mailbox"], entry["sender"], policy
                )
                _interestDataReplace(interestData, updated)
            elif column == 6:
                current = interestPersonPolicyGet(
                    interestData, entry["mailbox"], entry["sender"]
                )
                policy = _policyShift(current, ("no", "auto", "yes"), direction)
                updated = interestPersonPolicySet(
                    entry["mailbox"], entry["sender"], policy
                )
                _interestDataReplace(interestData, updated)
                _interestEntryClassify(entry, interestData)
            else:
                return
            _interestEntryRefresh(entry, interestData)
            _interestTableRowUpdate(table, row, entry)

        def _digestSenderRowsRefresh(self) -> None:
            table = self.query_one("#interest-table", DataTable)
            for index, entry in enumerate(senderRows):
                _interestEntryRefresh(entry, interestData)
                _interestTableRowUpdate(table, index, entry)

        def on_input_changed(self, event: Input.Changed) -> None:
            """Filter grouped Proposed Moves without changing the stored plan."""
            if event.input.id != "proposal-filter":
                return
            plan = snapshot.get("migrationPlan")
            if not plan:
                return
            table = self.query_one("#proposal-table", DataTable)
            rows = _proposalRowsFiltered(plan, event.value)
            table.clear(columns=False)
            for row in rows:
                table.add_row(*(Text(str(cell)) for cell in row))
            self.query_one("#proposal-filter-status", Static).update(
                f"Showing {len(rows)} of {len(_proposalRows(plan))} grouped moves"
            )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle planning refresh, review decisions and filing rules."""
            if event.button.id == "filing-add-parent":
                self._filingParentAdd()
                return
            if event.button.id == "filing-save-domain":
                self._filingDomainSave()
                return
            if event.button.id == "filing-save-sender":
                self._filingSenderSave()
                return
            if event.button.id == "resolve-sender":
                self._senderResolutionSave(snapshot.get("migrationPlan"))
                return
            if event.button.id in ("run-planning", "refresh-planning"):
                self.exit("runPlanning")

        def on_data_table_row_highlighted(
            self, event: DataTable.RowHighlighted
        ) -> None:
            """Keep the filing editors aligned with the selected domain."""
            if event.data_table.id != "filing-table":
                return
            if event.cursor_row < 0 or event.cursor_row >= len(filingRows):
                return
            self._filingEditorsFill(filingRows[event.cursor_row])

        def _senderResolutionSave(self, plan: dict | None) -> None:
            if not plan:
                return
            table = self.query_one("#review-table", DataTable)
            chooser = self.query_one("#review-folder", Select)
            status = self.query_one("#review-resolution-status", Static)
            row = table.cursor_row
            if row < 0 or row >= len(plan["reviewQueue"]):
                status.update("Select a Review Queue row first.")
                return
            entry = plan["reviewQueue"][row]
            source = entry.get("source", {})
            sender = source.get("sender")
            targetMailbox = entry.get("targetMailbox")
            if not sender or not targetMailbox:
                status.update(
                    "This review item is not a sender-classification decision."
                )
                return
            selection = chooser.value
            if not isinstance(selection, tuple) or len(selection) != 2:
                status.update("Choose a canonical folder first.")
                return
            selectedMailbox, canonical = selection
            if selectedMailbox != targetMailbox:
                status.update(f"Choose a folder belonging to {targetMailbox}.")
                return
            from mailAgent.planResolution import senderResolutionSet

            senderResolutionSet(
                entry["mailbox"],
                sender,
                targetMailbox,
                canonical,
            )
            self.exit("runPlanning")

        def _filingParentAdd(self) -> None:
            _filingParentAdd(self, snapshot, filingRows)

        def _filingDomainSave(self) -> None:
            _filingRuleSave(self, snapshot, filingRows, "domain")

        def _filingSenderSave(self) -> None:
            _filingRuleSave(self, snapshot, filingRows, "sender")

        def _filingRefresh(self) -> None:
            _filingRefresh(self, snapshot, filingRows)

        def _filingEditorsFill(self, row: dict) -> None:
            _filingEditorsFill(self, snapshot, row)

    return MailboxAudit()


def auditShow(snapshot: dict) -> str | None:
    """Display audit facts and return any requested follow-up workflow."""
    return auditAppBuild(snapshot).run()


def _interestPane(
    senderRows: list[dict],
    interestData: dict,
    issue: str | None,
    filingPlan: dict,
    filingRows: list[dict],
    filingIssue: str | None,
) -> ComposeResult:
    with TabPane("Inbox Digest", id="inboxInterest"):
        with TabbedContent(id="digest-menu"):
            with TabPane("Senders", id="digestSenders"):
                yield Static(
                    "Click Digest or Person, then use ← / →. Digest: Auto follows the "
                    "reason policy, In always includes, Out always excludes. Person: "
                    "Auto uses mailAgent's judgement, Yes/No corrects it.",
                    markup=False,
                )
                if issue:
                    yield Static(issue, markup=False)
                table = _DigestPolicyTable(id="interest-table", cursor_type="cell")
                # Keep the table constrained to the remaining tab height so DataTable
                # performs its own vertical scrolling and keeps the cursor visible.
                table.styles.height = "1fr"
                table.add_columns(
                    "Mailbox",
                    "Sender",
                    "#",
                    "Reason",
                    "Effective",
                    "Digest",
                    "Person",
                )
                for entry in senderRows:
                    table.add_row(*_interestTableRow(entry))
                yield table
                if not senderRows:
                    yield Static("No Inbox sender headers available", markup=False)
            with TabPane("Include Reasons", id="digestReasons"):
                yield Static(
                    "Click a Setting cell, then use ← / → to change Out ↔ Manual ↔ In. "
                    "Changes are saved immediately.",
                    markup=False,
                )
                policies = interestReasonPolicies(interestData)
                reasonTable = _DigestPolicyTable(
                    id="digest-reason-table", cursor_type="cell"
                )
                reasonTable.styles.height = "1fr"
                reasonTable.add_columns("Reason", "Setting")
                for reason in interestReasons():
                    reasonTable.add_row(
                        Text(reason.title()), Text(policies[reason].title())
                    )
                yield reasonTable
                yield Static("", id="digest-reason-status", markup=False)
            yield from _filingPane(filingPlan, filingRows, filingIssue)


def _filingParentAdd(app, snapshot: dict, filingRows: list[dict]) -> None:
    """Record a proposed parent for the selected domain without creating it."""
    row = _filingSelectedRow(app, filingRows)
    if not row:
        _filingStatus(app, "Select a filing domain first.")
        return
    try:
        from mailAgent.filing import filingNameNormalize, filingParentAdd, filingPath

        parent = filingNameNormalize(app.query_one("#filing-parent-name", Input).value)
        discovered = set(
            (snapshot.get("filingPlan") or {})
            .get("parents", {})
            .get(row["mailbox"], [])
        )
        if parent in discovered:
            _filingStatus(app, f"{parent} already exists.")
            return
        filingParentAdd(row["mailbox"], parent, filingPath())
        _filingRecompute(app, snapshot, filingRows)
    except ValueError as error:
        _filingStatus(app, str(error))
        return
    _filingStatus(app, f"Proposed parent {parent}. No folder was created.")


def _filingRuleSave(app, snapshot: dict, filingRows: list[dict], kind: str) -> None:
    """Persist a domain rule or exact sender override and refresh the plan."""
    row = _filingSelectedRow(app, filingRows)
    if not row:
        _filingStatus(app, "Select a filing domain first.")
        return
    try:
        parent, child, proposed = _filingChoiceRead(app, snapshot, row)
        saved = (
            _filingDomainStore(row, parent, child, proposed)
            if kind == "domain"
            else _filingSenderStore(app, row, parent, child, proposed)
        )
        _filingRecompute(app, snapshot, filingRows)
    except ValueError as error:
        _filingStatus(app, str(error))
        return
    _filingStatus(app, f"Saved {saved} -> {parent}/{child}. Mail was not changed.")


def _filingDomainStore(row: dict, parent: str, child: str, proposed: bool) -> str:
    from mailAgent.filing import filingDomainSet, filingPath

    filingDomainSet(
        row["mailbox"], row["domain"], parent, child, proposed, filingPath()
    )
    return row["domain"]


def _filingSenderStore(app, row: dict, parent: str, child: str, proposed: bool) -> str:
    from mailAgent.filing import filingDomainExtract, filingPath, filingSenderSet
    from mailAgent.senderAddress import senderNormalize

    sender = senderNormalize(app.query_one("#filing-sender", Input).value)
    if not sender:
        raise ValueError("Enter an exact sender address")
    if filingDomainExtract(sender) != row["domain"]:
        raise ValueError(f"Sender is not in {row['domain']}")
    filingSenderSet(row["mailbox"], sender, parent, child, proposed, filingPath())
    return sender


def _filingChoiceRead(app, snapshot: dict, row: dict) -> tuple[str, str, bool]:
    from mailAgent.filing import filingNameNormalize

    plan = snapshot.get("filingPlan") or {}
    discovered = set(plan.get("parents", {}).get(row["mailbox"], []))
    selection = app.query_one("#filing-parent", Select).value
    if not isinstance(selection, str) or selection == "__add__":
        parent = filingNameNormalize(app.query_one("#filing-parent-name", Input).value)
    else:
        parent = filingNameNormalize(selection)
    child = filingNameNormalize(app.query_one("#filing-child", Input).value)
    return parent, child, parent not in discovered


def _filingRecompute(app, snapshot: dict, filingRows: list[dict]) -> None:
    from mailAgent.filing import filingPath, filingPlanBuild, filingRulesLoad

    context = snapshot.get("filingContext")
    if not context:
        raise ValueError("Filing context is unavailable")
    snapshot["filingPlan"] = filingPlanBuild(
        context, snapshot, filingRulesLoad(filingPath())
    )
    _filingRefresh(app, snapshot, filingRows)


def _filingRefresh(app, snapshot: dict, filingRows: list[dict]) -> None:
    """Replace the filing table from the current plan, keeping the selected domain."""
    previous = _filingSelectedIdentity(app, filingRows)
    plan = snapshot.get("filingPlan") or {}
    filingRows.clear()
    filingRows.extend(plan.get("rows", []))
    table = app.query_one("#filing-table", DataTable)
    table.clear(columns=False)
    for row in filingRows:
        table.add_row(*(Text(str(cell)) for cell in _filingTableCells(row)))
    _filingCursorRestore(table, filingRows, previous)
    app.query_one("#filing-summary", Static).update(_filingSummary(plan))
    app.query_one("#filing-overrides", Static).update(_filingOverrideText(plan))
    app.query_one("#filing-empty", Static).update(
        "" if filingRows else "No Inbox domains to file"
    )
    selected = _filingSelectedRow(app, filingRows)
    if selected:
        _filingEditorsFill(app, snapshot, selected)


def _filingCursorRestore(table: DataTable, filingRows: list[dict], previous) -> None:
    if not previous:
        return
    for index, row in enumerate(filingRows):
        if (row["mailbox"], row["domain"]) == previous:
            table.move_cursor(row=index)
            return


def _filingSelectedIdentity(app, filingRows: list[dict]):
    row = _filingSelectedRow(app, filingRows)
    if not row:
        return None
    return row["mailbox"], row["domain"]


def _filingEditorsFill(app, snapshot: dict, row: dict) -> None:
    """Show the selected domain's parent and suggested folder."""
    if not app.query("#filing-parent") or not app.query("#filing-child"):
        return
    plan = snapshot.get("filingPlan") or {}
    chooser = app.query_one("#filing-parent", Select)
    chooser.set_options(_filingParentOptions(row["mailbox"], plan))
    if row.get("parent"):
        chooser.value = row["parent"]
    app.query_one("#filing-child", Input).value = (
        row.get("folder") or row.get("suggestion") or ""
    )


def _filingSelectedRow(app, filingRows: list[dict]) -> dict | None:
    if not filingRows:
        return None
    table = app.query_one("#filing-table", DataTable)
    row = table.cursor_row
    if not isinstance(row, int) or row < 0 or row >= len(filingRows):
        row = 0
    return filingRows[row]


def _filingStatus(app, message: str) -> None:
    app.query_one("#filing-status", Static).update(message)


def _filingPane(
    filingPlan: dict, filingRows: list[dict], filingIssue: str | None
) -> ComposeResult:
    """Domain filing review. Saving a rule does not move mail or create folders."""
    with TabPane("Filing", id="inboxFiling"):
        yield Static(_filingSummary(filingPlan), id="filing-summary", markup=False)
        if filingIssue:
            yield Static(filingIssue, markup=False)
        table = DataTable(id="filing-table", cursor_type="row")
        table.styles.height = 12
        table.add_columns(
            "Domain", "Archive", "Inbox", "Parent", "Folder", "Destination", "Status"
        )
        for row in filingRows:
            table.add_row(*(Text(str(cell)) for cell in _filingTableCells(row)))
        yield table
        yield Static(
            "" if filingRows else "No Inbox domains to file",
            id="filing-empty",
            markup=False,
        )
        mailbox = filingRows[0]["mailbox"] if filingRows else ""
        options = (
            _filingParentOptions(mailbox, filingPlan)
            if mailbox
            else [("Add parent...", "__add__")]
        )
        yield Static(
            "Choose an existing parent or add one. A new parent is stored as a "
            "filing decision only; the folder is not created.",
            markup=False,
        )
        yield Select(options, prompt="Parent", id="filing-parent")
        yield Input(placeholder="New parent name", id="filing-parent-name")
        first = filingRows[0] if filingRows else {}
        yield Input(
            placeholder="Folder name",
            id="filing-child",
            value=first.get("folder") or first.get("suggestion") or "",
        )
        yield Input(placeholder="Exact sender override, optional", id="filing-sender")
        yield Button("Add parent", id="filing-add-parent")
        yield Button("Save domain rule", id="filing-save-domain", variant="primary")
        yield Button("Save sender override", id="filing-save-sender")
        yield Static(
            _filingOverrideText(filingPlan), id="filing-overrides", markup=False
        )
        yield Static("", id="filing-status", markup=False)


def _filingParentOptions(mailbox: str, plan: dict) -> list[tuple[str, str]]:
    discovered = list(plan.get("parents", {}).get(mailbox, []))
    proposed = [
        name
        for name in plan.get("proposedParents", {}).get(mailbox, [])
        if name not in discovered
    ]
    options = [(name, name) for name in discovered]
    options.extend((f"{name} (proposed)", name) for name in proposed)
    options.append(("Add parent...", "__add__"))
    return options


def _filingSummary(plan: dict) -> str:
    return (
        "Read Inbox mail can be filed. Unread Inbox mail stays in the Inbox. "
        f"Proposals: {len(plan.get('proposals', []))}. "
        f"Need a choice: {len(plan.get('reviews', []))}. "
        "Saving a rule does not move mail or create folders. Filing execution is disabled."
    )


def _filingOverrideText(plan: dict) -> str:
    lines = [
        f'{item["sender"]} -> {item["canonical"]} ({item["mailbox"]})'
        for item in plan.get("senderOverrides", [])
    ]
    if not lines:
        return "No exact sender overrides."
    return "Sender overrides: " + "; ".join(lines)


def _filingTableCells(row: dict) -> tuple:
    return (
        row.get("domain", ""),
        row.get("archive", ""),
        str(row.get("inboxCount", "")),
        row.get("parent", ""),
        row.get("folder", ""),
        row.get("canonical", ""),
        row.get("status", ""),
    )


def _interestRows(snapshot: dict, interestData: dict) -> list[dict]:
    grouped = {}
    for mailbox in snapshot["mailboxes"]:
        identity = mailbox["id"]
        for message in mailbox.get("inboxInventory", {}).get("messages", []):
            sender = message.get("sender")
            if not sender:
                continue
            key = (identity, sender)
            entry = grouped.setdefault(
                key,
                dict(
                    mailbox=identity,
                    sender=sender,
                    senderName="",
                    count=0,
                    subjects=[],
                ),
            )
            entry["count"] += 1
            if message.get("subject"):
                entry["subjects"].append(message["subject"])
            if message.get("senderName") and not entry["senderName"]:
                entry["senderName"] = message["senderName"]
    rows = []
    for entry in grouped.values():
        _interestEntryClassify(entry, interestData)
        _interestEntryRefresh(entry, interestData)
        rows.append(entry)
    return sorted(
        rows,
        key=lambda entry: (
            not entry["included"],
            entry["reason"] != "person",
            entry["mailbox"],
            entry["sender"],
        ),
    )


def _interestEntryClassify(entry: dict, interestData: dict) -> None:
    _, reason = interestSuggest(
        entry["sender"],
        entry["subjects"],
        entry["senderName"],
        interestPersonPolicyGet(interestData, entry["mailbox"], entry["sender"]),
    )
    entry["reason"] = reason


def _interestEntryRefresh(entry: dict, interestData: dict) -> None:
    entry["senderPolicy"] = interestSenderPolicyGet(
        interestData, entry["mailbox"], entry["sender"]
    )
    entry["personPolicy"] = interestPersonPolicyGet(
        interestData, entry["mailbox"], entry["sender"]
    )
    entry["included"] = interestEffective(
        interestData,
        entry["mailbox"],
        entry["sender"],
        entry["reason"],
    )


def _interestTableRow(entry: dict) -> tuple[Text, ...]:
    return tuple(
        Text(value)
        for value in (
            entry["mailbox"],
            entry["sender"],
            str(entry["count"]),
            entry["reason"].title() if entry["reason"] else "Other",
            "In" if entry["included"] else "Out",
            entry["senderPolicy"].title(),
            entry["personPolicy"].title(),
        )
    )


def _interestTableRowUpdate(table: DataTable, row: int, entry: dict) -> None:
    for column, value in enumerate(_interestTableRow(entry)):
        table.update_cell_at(Coordinate(row, column), value)


def _interestDataReplace(target: dict, updated: dict) -> None:
    target.clear()
    target.update(updated)


def _policyShift(current: str, values: tuple[str, ...], direction: int) -> str:
    index = values.index(current)
    index = max(0, min(len(values) - 1, index + direction))
    return values[index]


def _planPane(plan: dict | None) -> ComposeResult:
    """Always show Plan; expose planning detail as a second-level menu."""
    with TabPane("Plan", id="plan"):
        if plan is None:
            with VerticalScroll():
                yield Static(
                    "⚠ ACTION NEEDED: Refresh Plan to prepare the migration review.",
                    id="plan-summary",
                    markup=False,
                )
                yield Button(
                    "Refresh Plan",
                    id="run-planning",
                    variant="primary",
                )
            return

        with TabbedContent(id="plan-menu"):
            with TabPane("Summary", id="planSummary"):
                with VerticalScroll():
                    generated = plan.get("generatedAt")
                    if generated:
                        yield Static(
                            "Stored plan from " + generated,
                            id="plan-generated",
                            markup=False,
                        )
                    yield Static(
                        _planActionText(plan),
                        id="plan-action",
                        markup=False,
                    )
                    yield Button(
                        "Refresh Plan",
                        id="refresh-planning",
                        variant="primary",
                    )
                    yield Static(
                        "\n".join(planSummaryLines(plan)),
                        id="plan-summary",
                        markup=False,
                    )
            yield from _planningPanes(plan)


def _planActionText(plan: dict) -> str:
    reviews = len(plan.get("reviewQueue", []))
    if reviews:
        return f"⚠ ACTION NEEDED: {reviews} items need decisions — open Review Queue."
    mirrors = sum(
        proposal.get("requiresFolderCreation", False)
        for proposal in plan.get("proposals", [])
    )
    if mirrors:
        return (
            f"⚠ ACTION NEEDED: {mirrors} proposed moves need IMAP mirror folders; "
            "review Proposed Moves."
        )
    return "✓ No user decisions are currently required by this plan."


def _planningEntries(plan: dict, key: str) -> list:
    if key == "roleBoundaries":
        return plan.get("roleBoundaries", plan.get("excluded", []))
    return plan.get(key, [])


def _planningPanes(plan: dict) -> ComposeResult:
    specifications = (
        (
            "Mapping",
            "mappings",
            "Canonical archive folders and their IMAP equivalents",
            ("Mailbox", "Archive folder", "IMAP folder", "Status"),
        ),
        (
            "Proposed Moves",
            "proposals",
            "Grouped for review; individual message proposals remain in the plan",
            ("From", "Sender", "#", "Year", "To", "Why"),
        ),
        (
            "Review Queue",
            "reviewQueue",
            "Items that still need a decision",
            ("Mailbox", "Folder / message", "Reason"),
        ),
        (
            "Role Boundaries",
            "roleBoundaries",
            "How every configured mailbox participates in mailAgent planning",
            ("Mailbox", "Role", "Policy"),
        ),
    )
    for title, key, label, columns in specifications:
        with TabPane(title, id=key):
            yield Static(label, markup=False)
            if key == "proposals":
                yield Input(
                    placeholder="Filter by source, sender, year, destination or reason",
                    id="proposal-filter",
                )
                yield Static(
                    f"Showing {len(_proposalRows(plan))} grouped moves",
                    id="proposal-filter-status",
                    markup=False,
                )
            table = DataTable(
                id=(
                    "review-table"
                    if key == "reviewQueue"
                    else "proposal-table" if key == "proposals" else None
                ),
                cursor_type="row" if key in ("reviewQueue", "proposals") else "cell",
            )
            table.add_columns(*columns)
            sourceEntries = _planningEntries(plan, key)
            entries = (
                _proposalRows(plan)
                if key == "proposals"
                else [_planningRow(key, entry) for entry in sourceEntries]
            )
            for row in entries:
                table.add_row(*(Text(str(cell)) for cell in row))
            yield table
            if key == "reviewQueue":
                options = [
                    (
                        f'{mapping["mailbox"]} — {mapping["canonical"]}',
                        (mapping["mailbox"], mapping["canonical"]),
                    )
                    for mapping in plan["mappings"]
                    if mapping.get("localSelectable")
                ]
                yield Static(
                    "For an unclassified sender, select its Review Queue row, "
                    "choose the canonical folder, then save. The decision applies "
                    "to that sender in the source mailbox.",
                    markup=False,
                )
                yield Select(
                    options,
                    prompt="Choose canonical folder",
                    id="review-folder",
                )
                yield Button(
                    "Use folder for selected sender",
                    id="resolve-sender",
                    variant="primary",
                )
                yield Static("", id="review-resolution-status", markup=False)
            if not sourceEntries:
                yield Static("No entries", markup=False)


def _planningRow(key: str, entry: dict) -> tuple:
    if key == "mappings":
        status = entry.get(
            "issue", "Existing folder" if entry["imapExists"] else "Folder proposed"
        )
        return (
            entry["mailbox"],
            entry["canonical"],
            _imapFolderDisplay(entry["imap"]) if entry["imap"] else "Unavailable",
            status,
        )
    if key == "proposals":
        return _proposalRow(entry, {})
    if key == "reviewQueue":
        source = entry.get("source", {})
        rawFolder = source.get("folder", entry.get("folder", ""))
        folder = (
            _imapFolderDisplay(rawFolder)
            if source or entry.get("systemFolder")
            else str(rawFolder)
        )
        if "messageCount" in entry:
            count = entry["messageCount"]
            folder += f" ({count if count is not None else 'unknown'} messages)"
        sender = source.get("sender")
        if sender:
            folder = f"{folder} · {sender}" if folder else sender
        return entry["mailbox"], folder, entry["reason"]
    return entry["mailbox"], entry["role"], entry["reason"]


def _proposalRows(plan: dict) -> list[tuple]:
    """Group identical message-level proposals into compact review rows."""
    stores = {
        archive["mailbox"]: _storeDisplay(Path(archive["root"]).name)
        for archive in plan.get("archives", [])
        if archive.get("mailbox") and archive.get("root")
    }
    grouped = {}
    for entry in plan.get("proposals", []):
        row = _proposalRow(entry, stores)
        key = row[:2] + row[3:]
        grouped[key] = grouped.get(key, 0) + 1
    return [(key[0], key[1], count, *key[2:]) for key, count in sorted(grouped.items())]


def _proposalRowsFiltered(plan: dict, value: str) -> list[tuple]:
    """Filter grouped Proposed Moves using a case-insensitive text match."""
    rows = _proposalRows(plan)
    terms = [term for term in value.lower().split() if term]
    if not terms:
        return rows
    return [
        row
        for row in rows
        if all(term in " ".join(str(cell).lower() for cell in row) for term in terms)
    ]


def _proposalRow(entry: dict, stores: dict) -> tuple:
    source, destination = entry["source"], entry["destination"]
    sender = source.get("sender", "Unknown sender")
    sourceText = f'{source["mailbox"]} IMAP/{_imapFolderDisplay(source["folder"])}'
    destinationFolder = (
        str(destination.get("folder", ""))
        if destination.get("kind") == "local"
        else _imapFolderDisplay(destination.get("folder", ""))
    )
    if destination.get("kind") == "local":
        store = stores.get(
            destination.get("mailbox"), destination.get("mailbox", "Archive")
        )
        target = f"{store}/{destinationFolder}"
    else:
        target = f'{destination.get("mailbox", "")} IMAP/{destinationFolder}'.strip()

    classification = entry.get("classification")
    if classification:
        method = classification.get("method")
        evidence = classification.get("evidenceCount")
        reason = {
            "archiveSenderExact": "Archive history",
            "senderContainsFolderName": "Folder-name match",
            "userSenderDecision": "User decision",
        }.get(method, classification.get("reason", "Inferred"))
        if evidence and method == "archiveSenderExact":
            reason += f" ({evidence})"
    else:
        reason = (
            "Already correctly filed"
            if entry["action"] == "retain"
            else "Current folder matches archive"
        )
    if entry.get("requiresFolderCreation"):
        reason += "; create IMAP mirror"
    return (
        sourceText,
        sender,
        1,
        entry["year"],
        target,
        reason,
    )


def _imapFolderDisplay(folder: str) -> str:
    """Decode IMAP modified UTF-7 and render hierarchy with slashes."""
    from mailAgent.migrationPlanning import _imapNameDecode

    try:
        decoded = _imapNameDecode(folder)
    except (ValueError, UnicodeError):
        decoded = folder
    return decoded.replace(".", "/")


def _folderDisplay(folder: str) -> str:
    """Render a non-encoded hierarchy in the user-facing slash form."""
    return folder.replace(".", "/")


## utilities


def _foldersPane(snapshot: dict) -> ComposeResult:
    """Show IMAP and configured local archive folders in one user-facing table."""
    table = DataTable(id="folders-table")
    table.add_columns("Mailbox", "Store", "Folder", "Messages", "Unseen", "Type")
    rows = 0
    for mailbox in snapshot["mailboxes"]:
        for folder in mailbox.get("folders", []):
            rows += 1
            table.add_row(
                Text(mailbox["id"]),
                Text("IMAP"),
                Text(_imapFolderDisplay(folder["path"])),
                Text(str(folder.get("messages", ""))),
                Text(str(folder.get("unseen", ""))),
                Text(_folderKindDisplay(folder)),
            )
    for archive in snapshot.get("localArchives", []):
        if not archive.get("available"):
            rows += 1
            table.add_row(
                Text(archive["mailbox"]),
                Text(_storeDisplay(archive["name"])),
                Text("(archive unavailable)"),
                Text(""),
                Text(""),
                Text("Local archive"),
            )
            continue
        for folder in archive.get("folders", []):
            rows += 1
            table.add_row(
                Text(archive["mailbox"]),
                Text(_storeDisplay(archive["name"])),
                Text(folder["path"]),
                Text(""),
                Text(""),
                Text("Local archive"),
            )
    yield table
    if not rows:
        yield Static("No folders discovered", markup=False)


def _auditPanes(snapshot: dict) -> ComposeResult:
    """Render discovery results as user-facing tables rather than JSON."""
    with TabPane("Filters", id="filters"):
        yield from _filtersPane(snapshot)
    with TabPane("Conflicts", id="conflicts"):
        yield from _conflictsPane(snapshot)
    with TabPane("Changes", id="changes"):
        yield from _changesPane(snapshot)


def _filtersPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="filters-table")
    table.add_columns(
        "Mailbox", "Filter", "Enabled", "Condition", "Action", "Destination"
    )
    rows = 0
    for source in snapshot.get("sources", []):
        mailboxes = ", ".join(source.get("mailboxIds", [])) or source.get(
            "account", "Unknown"
        )
        for rule in source.get("filters", []):
            rows += 1
            actions = ", ".join(
                action["type"] + (f': {action["value"]}' if action.get("value") else "")
                for action in rule.get("actions", [])
            )
            destinations = ", ".join(
                _destinationDisplay(value) for value in rule.get("destinations", [])
            )
            table.add_row(
                Text(mailboxes),
                Text(rule.get("name", "")),
                Text(_enabledDisplay(rule.get("enabled"))),
                Text(" | ".join(rule.get("conditions", []))),
                Text(actions),
                Text(destinations),
            )
    yield table
    if not rows:
        yield Static(
            "No Thunderbird message filters discovered. "
            "Check the active Thunderbird profile if filters are expected.",
            markup=False,
        )


def _conflictsPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="conflicts-table")
    table.add_columns("Mailbox", "Filter", "Status", "Problem", "Destination")
    rows = _conflictRows(snapshot)
    for row in rows:
        table.add_row(*(Text(value) for value in row))
    yield table
    if not rows:
        yield Static("No conflicts discovered", markup=False)


def _conflictRows(snapshot: dict) -> list[tuple[str, str, str, str, str]]:
    """Return de-duplicated user-facing filter conflict rows."""
    identityMap = {}
    for source in snapshot.get("sources", []):
        for index, rule in enumerate(source.get("filters", [])):
            identity = f'{source["path"]}#{index}'
            identityMap[identity] = dict(
                filterName=rule.get("name", "Unnamed filter"),
                mailboxes=source.get("mailboxIds", []),
            )

    rows = set()
    for entry in snapshot.get("conflicts", []):
        metadata = identityMap.get(entry.get("filter", ""), {})
        name = (
            entry.get("filterName") or metadata.get("filterName") or "Multiple filters"
        )
        mailboxes = entry.get("mailboxes") or metadata.get("mailboxes") or []
        mailbox = ", ".join(mailboxes) if mailboxes else "Thunderbird"
        status = (
            "Warning"
            if entry.get("label") == "Warning/Conflict"
            else entry.get("label", "")
        )
        problem = entry.get("message", "")
        categories = entry.get("categories", [])
        if categories:
            problem += ": " + ", ".join(categories)
        rows.add(
            (
                mailbox,
                name,
                status,
                problem,
                _destinationDisplay(entry.get("target", "")),
            )
        )
    return sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3], row[4]))


def _changesPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="changes-table")
    table.add_columns("Change", "Mailbox", "Item", "Before", "After")
    rows = _changeRows(snapshot)
    for row in rows:
        table.add_row(*(Text(value) for value in row))
    yield table
    if not rows:
        yield Static("No changes since the previous snapshot", markup=False)


def _changeRows(snapshot: dict) -> list[tuple[str, str, str, str, str]]:
    """Render structural changes without exposing Thunderbird storage paths."""
    sourceMap = {
        source.get("path", ""): source for source in snapshot.get("sources", [])
    }
    rows = []
    for entry in snapshot.get("changes", []):
        kind = entry.get("kind", "")
        identity = entry.get("identity", "")
        mailbox, item = _changeIdentityDisplay(kind, identity, sourceMap)
        rows.append(
            (
                kind,
                mailbox,
                item,
                _changeValueDisplay(entry.get("before", "")),
                _changeValueDisplay(entry.get("after", "")),
            )
        )
    return rows


def _changeIdentityDisplay(kind: str, identity, sourceMap: dict) -> tuple[str, str]:
    if kind.startswith("filter ") and isinstance(identity, (list, tuple)):
        sourcePath = str(identity[0]) if identity else ""
        filterName = str(identity[1]) if len(identity) > 1 else "Unnamed filter"
        source = sourceMap.get(sourcePath, {})
        mailboxes = source.get("mailboxIds", [])
        mailbox = ", ".join(mailboxes) or source.get("account", "Thunderbird")
        return mailbox, filterName
    return _identityDisplay(identity)


def _changeValueDisplay(value) -> str:
    if isinstance(value, list):
        return ", ".join(_destinationDisplay(str(item)) for item in value)
    return str(value)


def _storeDisplay(name: str) -> str:
    """Hide Thunderbird's .sbd storage implementation suffix."""
    return name[:-4] if name.lower().endswith(".sbd") else name


def _folderKindDisplay(folder: dict) -> str:
    attributes = [attribute.lstrip("\\") for attribute in folder.get("attributes", [])]
    if attributes:
        return ", ".join(attributes)
    return "Folder"


def _enabledDisplay(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def _destinationDisplay(value: str) -> str:
    if not value:
        return ""
    if value.startswith("imap://"):
        from urllib.parse import unquote, urlsplit

        try:
            parsed = urlsplit(value)
            return _imapFolderDisplay(unquote(parsed.path.lstrip("/")))
        except ValueError:
            return value
    return _imapFolderDisplay(value)


def _identityDisplay(identity) -> tuple[str, str]:
    if isinstance(identity, (list, tuple)) and len(identity) >= 2:
        return str(identity[0]), _imapFolderDisplay(str(identity[1]))
    return "", str(identity)
