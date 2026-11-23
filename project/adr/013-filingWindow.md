# 013: One Qt filing window replaces the zenity dialogs

- Status: Accepted
- Date: 2026-11-23
- Requirements: [005](../requirements/features/005-pdfFilerSuggestions.md)
- Amends: [ADR 011](011-pdfFilerPython.md) (the GUI layer)

## Context

The first `1.4a7` build asked about each PDF in a small zenity Yes/No box
(File / Change… / Skip), with page 1 in a separate feh window placed by
wmctrl. In use this was unsatisfactory:

- the box was cramped;
- the filed name wrapped over several lines;
- changing anything meant leaving it for a chain of further dialogs.

A tkinter window was tried next. It worked, but conda's Tk has no Xft font
support, and the user prefers Qt or a TUI for interfaces. A TUI cannot show
the scanned page, which is the point of the window.

## Decisions

1. **One window per run, built with Qt (PySide6).** PySide6 is already in
   `py312`, and the user's other projects use it.
   - Page 1 is on the left, drawn by Qt's own PDF renderer (QtPdf), with
     paging and Fit page / Fit width.
   - On the right are the folder (the suggestion and other likely folders,
     plus Browse…), type, date and label, already filled in and editable.
2. **The filed name is shown whole, on one line**, and updates as any field
   changes. Problems are shown at once and disable **File**: no folder, a bad
   or future date, or a name already taken. A copy already filed turns
   **File** into **Trash duplicate**.
3. **File / Skip / Stop**, with Enter for File and Esc for Skip. Closing the
   window stops the run. The same window is used when there is no
   suggestion, with the folder left empty.
4. **The UI follows the repository's UI file layout:**
   `ui/filingWindow.py` reads as an outline of the window, the page viewer is
   the reusable `ui/widgets/pageView.py`, and the colours are in
   `ui/styles/filingWindow.qss` on top of the desktop's own theme. The form
   logic is core (`form.py`), tested without a display, and `inbox.py`
   imports no GUI code.
5. **zenity, feh, wmctrl and tkinter are not used.** The window opens only
   when a PDF needs it, so an empty inbox, auto rules, `suggest` and
   `index show` need no display.

## Consequences

- Window tests drive the real Qt window off-screen
  (`QT_QPA_PLATFORM=offscreen`), so they need no display and show nothing on
  screen. A watchdog fails any test that leaves the window waiting.
- PySide6 is a dependency of the pdfFiler project (`pyproject.toml`,
  `environment.yml`).
