"""Keyboard interaction for editable Inbox Digest policy tables."""

from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.widgets import DataTable


class DigestPolicyTable(DataTable):
    """Edit digest policies directly with arrows or sender shortcuts."""

    BINDINGS = [
        Binding("left", "policy_positive", "", show=False, priority=True),
        Binding("right", "policy_negative", "", show=False, priority=True),
        Binding("i", "sender_in", "", show=False, priority=True),
        Binding("o", "sender_out", "", show=False, priority=True),
        Binding("a", "sender_auto", "", show=False, priority=True),
        Binding("y", "person_yes", "", show=False, priority=True),
        Binding("n", "person_no", "", show=False, priority=True),
    ]

    def action_policy_positive(self) -> None:
        """Move one step toward the positive choice: In or Yes."""
        self._shift(1)

    def action_policy_negative(self) -> None:
        """Move one step toward the negative choice: Out or No."""
        self._shift(-1)

    def action_sender_in(self) -> None:
        self._senderSet(5, 1)

    def action_sender_out(self) -> None:
        self._senderSet(5, -1)

    def action_sender_auto(self) -> None:
        self._senderSet(5, 0)

    def action_person_yes(self) -> None:
        self._senderSet(6, 1)

    def action_person_no(self) -> None:
        self._senderSet(6, -1)

    def _shift(self, direction: int) -> None:
        handler = getattr(self.app, "_digestPolicyShift", None)
        if handler:
            handler(self, direction)

    def _senderSet(self, column: int, target: int) -> None:
        """Set one sender policy when its email-address cell is selected."""
        if self.id != "interest-table" or self.cursor_coordinate.column != 1:
            return
        row = self.cursor_coordinate.row
        if row < 0:
            return
        original = self.cursor_coordinate
        self.cursor_coordinate = Coordinate(row, column)
        try:
            # The underlying editor saturates at each end.  Move to the positive
            # end first so Auto can be reached deterministically in one step back.
            if target > 0:
                self._shift(1)
                self._shift(1)
            elif target < 0:
                self._shift(-1)
                self._shift(-1)
            else:
                self._shift(1)
                self._shift(1)
                self._shift(-1)
        finally:
            self.cursor_coordinate = original
