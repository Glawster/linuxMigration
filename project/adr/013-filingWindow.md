# 013: One tkinter filing window replaces the zenity dialogs

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

## Decisions

1. **One window per run, built with tkinter.** Page 1 is on the left, with
   paging and zoom. On the right are the folder (the suggestion and other
   likely folders, plus Browse…), type, date and label, already filled in
   and editable.
2. **The filed name is shown whole, on one line**, and updates as any field
   changes. Problems are shown at once and disable **File**: no folder, a bad
   or future date, or a name already taken. A copy already filed turns
   **File** into **Trash duplicate**.
3. **File / Skip / Stop**, with Enter for File and Esc for Skip. Closing the
   window stops the run. The same window is used when there is no
   suggestion, with the folder left empty.
4. **The form logic is core** (`form.py`), tested without a display. The
   window (`ui/`) only shows it. `inbox.py` no longer imports any GUI code.
5. **tkinter is already in the `py312` environment.** Its Tk build has no Xft
   support, so the window picks the best available sans font: Ubuntu,
   DejaVu, Noto and so on, then texgyreheros.
6. **zenity, feh and wmctrl are no longer used.** The window opens only when
   a PDF needs it, so an empty inbox, auto rules, `suggest` and `index show`
   need no display.

## Consequences

- Window tests drive the real window on the display (`tests/test_window.py`,
  skipped without one). A watchdog fails any test that leaves it waiting.
- Installing an Xft build of Tk (`conda install -c conda-forge "tk=*=xft*"`)
  would give anti-aliased fonts; this is optional.
