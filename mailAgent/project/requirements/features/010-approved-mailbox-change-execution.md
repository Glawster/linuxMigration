# REQ-010 Approved mailbox change execution

## Status

InProgress

## Purpose

Enable mailAgent to perform reviewed mailbox changes safely after the planning and approval work in REQ-004, REQ-008 and REQ-009.

This requirement introduces the first mutation-capable execution path. It must not reinterpret planning decisions while executing them. Execution consumes an approved plan, revalidates that the source still matches the approved identity, applies the requested change, verifies the result and records an audit trail.

## Scope

REQ-010 initially applies only to personal mailbox actions that have already been resolved and approved by the planning workflow.

Supported actions are:

- create an approved destination folder when required;
- file current/live-year read Inbox mail into the approved IMAP destination;
- archive older mail to the approved local archive destination using copy, verify, then source removal;
- apply an approved Ignore disposition by making no mailbox change and recording that the decision was honoured;
- apply an approved Junk disposition by setting the server-side junk/spam mark used by Thunderbird without moving or deleting the message directly.

Shared and support mailboxes remain outside this execution requirement unless a later requirement explicitly adds mutation policy for them.

## Authoritative local archive topology

There is one authoritative local mail archive store for the personal mailboxes. It is hosted on the local PC where mailAgent manages the Thunderbird Local Folders archive.

For the current installation:

- Andy's authoritative local archive is `myMail`;
- Kathy's authoritative local archive is `kathyMail`.

These are not per-device archives and must not be treated as data that is replicated automatically to every mail client.

IMAP is the shared/live mail view. Its folder structure is visible to any device connected to the corresponding mailbox. For example, Kathy can use her MacBook to access her account and see the IMAP folder structure, but that MacBook does not have access to the authoritative local `kathyMail` archive hosted on the local PC.

The practical visibility model is therefore:

```text
current/live mail
    -> IMAP
    -> visible to all connected clients

older/archive mail
    -> myMail or kathyMail on the authoritative local PC
    -> no longer visible to other IMAP-only clients once removed from the server
```

Archiving old mail locally is therefore an intentional change in availability. For Kathy, mail moved from IMAP into `kathyMail` remains available from the machine hosting that local archive, but is no longer expected to be visible from her MacBook or another IMAP-only client.

Execution must not:

- assume that `myMail` or `kathyMail` exists on another client machine;
- create a second local archive copy merely because the same mailbox is used from another device;
- attempt to synchronise the local archive to Kathy's MacBook or any other client;
- treat absence of the local archive on another device as an error.

The canonical local archive remains the default destination for pre-live-year personal mail unless an approved filing rule explicitly selects the other authoritative personal archive as described below. No replication or remote archive access is implied by such an override.

## Explicit cross-archive filing override

REQ-009 may produce an explicit per-rule **archive store** override for personal mail. This separates the source mailbox from the local archive that owns the filed copy.

The default remains:

```text
Andy source  -> myMail
Kathy source -> kathyMail
```

A user may deliberately approve a cross-archive local destination, for example:

```text
source mailbox: Andy
archive store:  kathyMail
path:           Finance/Insurance
```

Execution must treat `source mailbox` and `archive store` as separate approved facts. It must never infer a cross-archive destination merely because an equivalent folder name exists in the other archive.

For the initial implementation, a cross-archive override applies only to **local archive filing**. It does not authorise moving current/live-year Andy mail into Kathy's IMAP account, or vice versa. Live-year File actions continue to target the source mailbox's own approved IMAP taxonomy unless a later requirement explicitly introduces cross-account IMAP filing.

A cross-archive action therefore requires all of the normal old-mail safeguards plus explicit approval of the destination archive store. The executor must verify that the selected archive store is one of the configured authoritative personal archives and that the approved Parent/Folder path belongs to that store's taxonomy or is explicitly approved for creation there.

## Safety boundary

Mutation remains disabled unless every action is explicitly executable in the stored plan.

An action may execute only when all of the following are true:

1. the plan schema is supported;
2. the plan was produced from the current configuration and mailbox identity;
3. the action has an approved disposition and destination where one is required;
4. the source message is still identifiable by mailbox, folder, UIDVALIDITY and UID;
5. the source message still satisfies the eligibility conditions recorded by the plan;
6. the destination has not changed since approval;
7. the action has not already completed successfully.

Any failed precondition leaves the source unchanged and records the action as blocked or stale.

## Execution identity

Each executable action must carry enough immutable identity to prevent acting on the wrong message after the plan was produced.

At minimum record:

- source mailbox id;
- source folder;
- UIDVALIDITY;
- UID;
- approved disposition;
- approved destination kind when relevant;
- approved archive store when the destination kind is local;
- approved canonical destination when relevant;
- whether folder creation was approved;
- the decision source and approval state;
- a stable execution action id.

A changed UIDVALIDITY invalidates the action. mailAgent must not guess a replacement UID.

## File disposition

### Live-year IMAP filing

For an approved live-year File action:

1. re-open the source mailbox and verify UIDVALIDITY;
2. verify the source UID still exists;
3. create the approved IMAP folder only when folder creation was explicitly approved;
4. copy or move using IMAP operations that can be verified;
5. verify the destination contains the intended message before treating the action as complete;
6. remove the source copy only after destination verification when the chosen IMAP operation requires separate removal;
7. record the result.

A retry must not create a duplicate destination message.

Cross-archive overrides do not change this path: live-year execution remains within the source mailbox's own IMAP account.

### Local archive filing

For an approved old-mail File action, removal from IMAP must follow copy -> verify -> remove.

The destination is the explicitly approved authoritative local archive store. Normally this is `myMail` for Andy and `kathyMail` for Kathy; an approved REQ-009 cross-archive rule may instead target the other configured personal archive.

1. verify the approved archive-store identity and canonical path;
2. copy the complete source message into that canonical local Thunderbird archive;
3. verify that the local copy is readable and corresponds to the intended source message;
4. only after verification, remove the source message from IMAP;
5. record the archive-store identity, archive identity and source-removal result.

If local verification fails, the source message must remain in IMAP.

Local archive writes must preserve Thunderbird-compatible storage and must not invent a second archive format.

## Ignore disposition

Ignore is an execution decision with no mailbox mutation.

When an approved Ignore action is executed:

- leave the message in INBOX;
- do not change read state;
- do not change flags;
- do not move, copy or delete the message;
- mark the execution action complete in the audit state so repeated runs do not keep presenting it as pending.

## Junk disposition

Junk is a flag/metadata action, not a mailAgent folder move.

When an approved Junk action is executed:

- set the server-side junk/spam state compatible with Thunderbird for that account;
- do not directly move or delete the message;
- do not create a Thunderbird filter;
- verify that the junk state was applied;
- allow Thunderbird/account rules to perform any subsequent folder movement.

If the account's supported junk-mark mechanism cannot be determined safely, block the action rather than guessing.

## Folder creation

Folder creation must be a separately approved fact in the plan.

mailAgent may create only the exact canonical path approved by the plan. It must not create additional inferred parents or siblings during execution.

For a local cross-archive action, folder creation approval is scoped to the selected archive store; approval to create `Finance/Insurance` in `myMail` does not authorise creation of the same path in `kathyMail`.

Creation must be idempotent: an already existing destination is success when it is the expected destination.

## Confirmation and execution control

A stored plan being approved is necessary but not sufficient to mutate mail.

The user must start an execution operation explicitly from the TUI. The execution screen must show a concise summary of the number and kind of pending actions before the run starts.

The mutation path must not be invoked by normal discovery, audit, planning, plan refresh or TUI startup.

## Execution state and audit log

Persist execution state under `~/.local/state/mailAgent/`.

For each action record at least:

- action id;
- timestamp started;
- timestamp completed or failed;
- source identity;
- disposition;
- destination archive store where applicable;
- destination where applicable;
- result status;
- verification result;
- error summary when blocked or failed.

Do not store message bodies, credentials or authentication secrets in the execution log.

Execution state must support safe restart after interruption.

## Idempotency and restart

Execution must be retry-safe.

After a process interruption or network failure, a later run must determine whether each action is:

- not started;
- completed and verified;
- partially completed and requiring verification;
- blocked/stale;
- failed and retryable.

mailAgent must verify current state before repeating any copy, folder creation, move or flag operation.

## Failure handling

One failed action must not corrupt the remaining plan.

The executor should continue with independent safe actions unless the failure indicates that the mailbox identity, UIDVALIDITY, credentials or execution environment is no longer trustworthy.

Failures must be visible in the TUI and retained in the audit state.

## TUI

Add an execution view separate from planning/review.

It should show:

- executable action count;
- File, Ignore and Junk counts;
- folder creations required;
- blocked/stale count;
- execution progress;
- completed/failed counts;
- latest error summary.

Cross-archive local actions must be visibly distinguishable before execution, including both source mailbox and destination archive store.

The user must be able to review the pending summary before starting execution.

Planning and review views remain non-mutating.

## Implementation boundaries

Keep execution logic independent of Textual widgets.

Suggested separation:

- plan validation and executable-action selection;
- IMAP mutation primitives;
- local archive write/verification primitives;
- execution journal/state;
- orchestration/retry logic;
- TUI presentation.

Mutation primitives should be small and testable. Tests must use fakes/fixtures and must not require the user's real mailboxes.

## Acceptance criteria

- normal audit/planning remains read-only;
- execution can start only by an explicit user action;
- only approved executable actions are considered;
- stale UIDVALIDITY or missing source UIDs block an action without guessing;
- approved IMAP folder creation is exact and idempotent;
- live-year File actions reach the approved IMAP destination and are verified;
- cross-archive overrides do not permit live-year cross-account IMAP filing;
- old-mail File actions use copy -> verify -> remove and preserve the source on verification failure;
- old-mail File actions default to the source mailbox's local archive but may target the other configured personal archive only when that archive store is explicitly approved in the plan;
- `myMail` and `kathyMail` are treated as the single authoritative local archives on the local PC rather than per-device stores;
- IMAP remains the shared/live view available to other connected devices;
- archiving old mail locally may intentionally make it unavailable to IMAP-only clients such as Kathy's MacBook;
- execution does not create or synchronise additional local archive copies on other client devices;
- a cross-archive action records and verifies both source mailbox and destination archive-store identity;
- Ignore performs no mailbox mutation and can be completed idempotently;
- Junk applies and verifies the account's supported junk state without a direct mailAgent move;
- completed actions are not duplicated on retry;
- interrupted runs can resume safely;
- execution results are persisted under `~/.local/state/mailAgent/` without bodies or secrets;
- shared/support mailboxes are not mutated;
- full project tests and checks pass before integration.


## Delivered increments

The first increment delivered pure plan validation and durable execution
journaling. The next narrow increment adds exact approved IMAP destination
creation and one explicitly confirmed live-year File action using copy ->
verify destination -> remove source, with durable partial-outcome reconciliation
and fake-mailbox interruption tests. It is a core API only; normal CLI/TUI
workflows remain read-only.

See [Execution boundary](../../../documentation/executionBoundary.md) for API
contracts, verification requirements, connection ownership and restart policy.
An uncertain COPY without a verifiable destination blocks rather than copying
again. No real mailbox has been changed to validate this increment.

Next broaden proven single-message execution to batches, then local archive,
then Junk. Keep orchestration and TUI presentation separate from core modules.

## Change history

- 2026-10-12: Add explicit per-rule local archive-store overrides. Cross-archive filing is local-archive only; live-year mail remains within the source mailbox's IMAP account.
