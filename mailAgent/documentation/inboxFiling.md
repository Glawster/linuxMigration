# Inbox filing

mailAgent can plan where read Inbox mail belongs. The Inbox stays a working
queue: unread mail remains there, and this phase does not move messages or
create folders.

The behaviour is specified by
[REQ-009](../project/requirements/features/009-read-inbox-filing.md). Live-year
and local-archive destinations continue to follow
[the mailbox model](mailboxModel.md).

## What is eligible

For a personal mailbox, and for the legacy mailbox that migrates into one:

- mail outside `INBOX` is ignored by Inbox filing;
- unread `INBOX` mail is left unchanged and is not a filing action;
- read (`\Seen`) `INBOX` mail is eligible;
- eligible mail is given a destination only when that destination is safe;
- ambiguous or unresolved read mail stays in `INBOX` and is shown for review.

A missing FLAGS response is treated as not known to be read, so it is not filed.

## Whose archive is used

Andy and Kathy keep independent taxonomies, discovered from `myMail` and
`kathyMail`. A rule saved for one person is not copied to the other.

The legacy mailbox reuses its personal target's rules. A live-year message
targets that person's IMAP mirror. An older message targets the same canonical
folder in that person's local archive.

Shared and support mailboxes are excluded.

## Domains, parents and folders

Senders are grouped by registrable organisation domain. The boundary comes
from the Public Suffix List shipped with the `publicsuffixlist` package, so
`amazon.co.uk`, `city.kawasaki.jp` and `pvt.k12.wy.us` keep the suffix that
list assigns. mailAgent does not keep its own suffix catalogue and does not
download a new list while it runs.

The full list and its ICANN section must agree before a domain is used
automatically. When they do not, the host is shown for you to clarify. That
covers a host that is only a public suffix, an unknown suffix, and a private
suffix boundary such as `shop.blogspot.com` (the list can read that as the
shop or as `blogspot.com`). Enter the organisation domain in the Filing
panel, or leave it blank to confirm the domain shown. A saved confirmation
still does not move mail. A one-label suffix such as `com`, or a registry
suffix such as `co.uk`, is not accepted as an organisation domain. An apex
the list does not split, such as `nhs.uk`, can be confirmed.

An exact sender override wins over the domain rule, and either user decision
wins over archive history. Until an uncertain domain is confirmed, archive
history is not used to choose a destination for that host.

Parents are the first level of the local archive only. `Shopping/Amazon/Orders`
contributes the parent `Shopping`. Deeper names are not extra parents.

`Add parent` records a proposed parent in the filing rules. It does not create
a Thunderbird or local folder. The plan status distinguishes:

| Status | Meaning |
| --- | --- |
| Existing | The parent and the canonical folder already exist |
| Proposed child | The parent exists and the child folder does not |
| Proposed parent + child | The parent itself is not in the archive yet |
| Needs choice | No safe destination has been resolved |
| Ignore | Leave matching read mail in Inbox |
| Junk | Record a future junk mark; no folder move |

Archive history is used only when one canonical folder is a strong match for
that exact sender. A folder-name guess is not sufficient, and the plan keeps
the history evidence on the proposal.

## Rules file

Durable rules live at:

```text
~/.config/mailAgent/filing-rules.json
```

The file is mailbox-specific and can store domain rules, exact sender
overrides, a confirmed organisation domain for a host the suffix list left
uncertain, proposed parent names and the canonical `Parent/Child` path. It is
written atomically with user-only permissions. It has a schema version and it
must not contain passwords, tokens or message content.

Saving a rule is preference data. It still does not change the mailbox.

## Proposals

A read Inbox scan produces a filing plan. Each proposal records the source
mailbox, `INBOX`, UID, UIDVALIDITY, the read state used for eligibility, the
sender, the domain, the canonical destination, whether that destination is an
IMAP mirror or a local archive path, why it was chosen, whether folder creation
would be required, and that execution is not permitted.

Live-year mail targets the canonical IMAP mirror when it already exists, or
names a mirror that would have to be created later. Older mail targets the
canonical local archive path. Creating that folder, copying the message and
removing the server copy are not performed. A local proposal records
copy-then-verify-then-remove as the future removal policy and keeps source
removal disallowed until that verification exists.

Thunderbird filters continue to be discovered and shown. Filing does not create
or require them.

## Review in the TUI

Open **Moving Mail** on the main menu. When decisions are needed, the summary
uses amber **ACTION NEEDED** text with the next step. Status cells and the
selected row's status use the same amber highlight for missing choices,
uncertain domains and proposed folders. Otherwise the summary explains that
read mail may be filed and this phase changes neither folders nor mail.
The top banner explicitly says Execute is not available in the TUI yet.
Plan also highlights required review or refresh actions in amber. Text labels
identify the action as well as colour. The table takes
most of the panel and scrolls on its own. Each row is one organisation domain
and shows the archive (`myMail` or `kathyMail`), how many current Inbox
messages it represents, the parent, the folder, the canonical destination and
the status.

Right-click **ACTION NEEDED**, or focus it with Tab and press Enter, to go
to the relevant controls. Moving Mail selects the first domain needing a
decision and focuses its domain or folder field. Proposed folders open their
folder field for review. In Plan, the shortcut opens Review Queue or Proposed
Moves; when no plan exists, it focuses Refresh Plan. Navigation never saves a
decision, starts a refresh or executes mailbox changes.

Saving a complete domain or sender decision clears that row's amber highlight
and updates the action count. A saved proposed folder keeps its descriptive
status but no longer asks for the same decision. The banner clears when no
decisions remain; navigating to a field alone does not resolve its action.

The selected row is the heading of the editor under the table, for example
`Filing: dpd.co.uk · kathyMail · 2 messages`. Choose a parent, edit the folder
name, and save a domain rule. **Add parent** records a filing decision only;
the folder is not created. The new-parent name is asked for only when you add
a parent.

Choose **File**, **Ignore**, or **Junk** in the editor and save a domain rule
or sender override. Ignore and Junk need no folder. Ignore leaves mail in the
Inbox; Junk records a future mark for Thunderbird's junk filter. Phase 1 only
records these decisions and status: it changes no flags, folders, or mail.
The plan's `dispositions` list is separate from its folder-move `proposals`.
Existing rules without a disposition remain File rules.

The organisation domain is shown in the heading. An editable organisation
domain appears only when the Public Suffix List does not identify one. Leave
that field blank to confirm the domain already shown, or type the organisation
domain you mean.

**Sender override** stays off the ordinary path. Use it only when one address
needs a different destination from the rest of its domain.

Neither action moves mail. Filing execution remains disabled. A later phase
would have to perform the reviewed folder creation, IMAP move, and verified
local archive steps under the existing migration safety rules.

The audit screen loads the shared organiseMyProjects stylesheet,
`myStyles.css`. Moving Mail layout, such as
the table height and the equal-width actions, stays in `filingView.tcss`.
