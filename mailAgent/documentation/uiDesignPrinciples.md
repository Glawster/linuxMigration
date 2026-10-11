# UI design principles

These principles capture the practical lessons from developing and refining the
mailAgent Textual interface. They are intended to guide future mailAgent work and
provide candidates for wider shared UI guidance across the user's applications.

## Design for the real workflow

Start with the sequence the user repeatedly performs, not with a generic form or
widget layout. A good screen should minimise the number of focus changes, clicks
and decisions required for the common path.

For repetitive review work, optimise for a loop such as:

```text
select item -> make decision -> save -> return to same place -> continue
```

Do not make the user repeatedly navigate back to the working list or recover
where they were.

## Preserve working context

Refreshing or recomputing data must preserve user context wherever possible.
That includes:

- selected item identity;
- table viewport/scroll position;
- active filter;
- multi-selection state;
- sensible focus after an edit.

A data refresh that leaves the same item selected but moves it to the bottom of
the screen still breaks the user's context.

## Separate action from status

Do not overload one field with both what the user intends and the current state
of the object.

For example, Moving Mail uses:

- **Action**: Choose, File, Ignore, Junk;
- **Status**: Existing, Proposed child, Proposed parent + child.

This makes the screen easier to scan and prevents labels such as `Needs choice`
from being confused with destination state.

## Use user-facing language

Labels should describe what the user needs to do rather than expose internal
state names. Prefer `Choose an Action` or `Choose` to implementation-oriented
phrases such as `Needs choice` when the purpose is to prompt a decision.

Warnings should be actionable: state what needs attention and the next available
action.

## Keep list and editor visually distinct

For list-heavy workflows, give most of the screen to the list and keep the
selected-item editor compact below or beside it.

The list provides context and throughput. The editor should contain only the
controls required to resolve the selected item.

Avoid allowing a large form to consume space needed for the main table.

## Prefer compact controls for high-throughput work

One-row inputs and selectors work well for dense review screens when the user is
processing many items. When a one-row control cannot spare space for a focus
border, indicate focus with background/foreground treatment instead of allowing
the border to obscure its value.

Controls that perform the same role should align and use consistent widths.
Dropdowns should be wide enough for expected values without wrapping.

## Use progressive disclosure

Keep exceptional operations out of the common path until they are needed.

Examples include:

- exact sender overrides;
- uncertain organisation-domain clarification;
- execution controls in an otherwise read-only planning screen.

Do not permanently occupy screen space with rare controls.

## Follow familiar desktop selection behaviour

Where mouse use is expected, use established selection conventions rather than
inventing a new marking system:

- click selects one item;
- Ctrl+click adds/removes an item;
- Shift+click selects a range;
- Ctrl+Shift+click extends a selection when supported.

Multi-selection must be visibly distinguishable from the normal cursor row.

## Provide keyboard and mouse parity

Frequent actions should be available from the keyboard while the relevant
widget has focus, without preventing equivalent mouse operation.

Use short, memorable keys for repetitive actions and show them once in the
standard footer/help area. Avoid duplicating the same shortcut legend elsewhere
on the screen.

## Make filtering explicit and non-destructive

A filter should change presentation only. It must not silently alter underlying
rules, approval state or selections.

The current filter should be visible, and switching back to the complete view
should restore access to all items without information loss.

## Make bulk changes predictable

Bulk editing should apply one explicit decision to the selected items while
preserving their independent identities in persistent state.

Do not replace several independent domain rules with one hidden group rule merely
because they were edited together.

Mixed existing values should be shown as mixed/blank rather than pretending the
selection has one value.

Operations that are unsafe or ambiguous in bulk, such as sender-specific
exceptions or unresolved organisation domains, should require individual
resolution.

## Keep feedback concise and local

After an edit, show a short result near the editor, for example:

```text
Saved: Shopping/Asda
```

Do not repeat global safety statements after every action when the screen already
makes the operating mode clear.

## Keep read-only planning separate from mutation

A planning/review screen must not quietly become an execution screen.

When mutation is disabled, state that clearly. Execution should use a separate,
explicit workflow with its own confirmation and progress presentation.

UI convenience must never weaken the safety boundary between proposing a change
and performing it.

## Size table columns deliberately

Columns should be allocated according to the value they provide, not simply
allowed to expand equally.

- give identity columns enough room to scan;
- keep numeric/count columns narrow;
- clip long destination text with an ellipsis rather than allowing it to bleed
  into adjacent columns;
- preserve important Action and Status columns at constrained widths;
- refit when the terminal size changes.

## Avoid duplicate information

If the same information is already visible in the footer, heading or selected
row, do not repeat it in another prominent control or line unless repetition is
necessary for clarity.

Every line in a dense interface should earn the space it consumes.

## Use shared visual roles, local layout rules

Shared application styling should define reusable visual roles such as colours,
headings, controls, warnings and focus treatment. Feature-specific stylesheets
should concentrate on layout, density and component-specific sizing.

Do not duplicate common palette rules into each application when a shared style
source exists.

## Do not fight the framework

Prefer public Textual events and widget APIs. Avoid relying on private methods or
internal attributes merely to achieve a visual effect or cursor behaviour.

When a framework default conflicts with a dense layout, override the smallest
well-defined piece rather than replacing the widget's normal behaviour wholesale.

## Test interactions, not only rendered values

UI tests should cover the workflows that matter to the user, including:

- focus order;
- Enter/Tab behaviour;
- keyboard shortcuts;
- mouse selection and modifier keys where practical;
- filtering;
- multi-selection;
- table resize/column fitting;
- selected-row and viewport preservation after a refresh;
- compact-control readability and contrast.

A UI can contain the correct data and still be difficult to use, so tests should
protect interaction behaviour as well as content.

## Refine from real use

Screens should be reviewed with realistic data volumes and at the terminal sizes
actually used. Small issues such as an obscured input value, a narrow dropdown,
a duplicated help line or a row jumping to the bottom of a table are difficult
to predict from code alone but significantly affect repeated use.

Treat those observations as design requirements rather than cosmetic polish.
