"""Accessible navigation from highlighted action-needed guidance."""

from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widgets import Static
from typing import Any


class ActionNeeded(Static):
    """Right-click or press Enter on a warning to visit its action controls."""

    can_focus = True
    BINDINGS = [Binding("enter", "navigate", "Go to action")]

    def __init__(self, content: str, **kwargs: Any) -> None:
        """Show how to follow an action-needed notice."""
        super().__init__(content, **kwargs)
        self.tooltip = (
            "ACTION NEEDED: right-click or focus and press Enter to go to the action."
        )

    class Navigate(Message):
        """Request navigation only; never perform the destination action."""

        def __init__(self, widget: "ActionNeeded") -> None:
            super().__init__()
            self.widget = widget

    def action_navigate(self) -> None:
        """Ask the owning app to navigate while this guidance needs action."""
        if self.has_class("action-needed"):
            self.post_message(self.Navigate(self))

    def on_click(self, event: Click) -> None:
        """Handle the terminal's right mouse button without changing mail."""
        if event.button == 3 and self.has_class("action-needed"):
            event.stop()
            self.focus()
            self.action_navigate()
