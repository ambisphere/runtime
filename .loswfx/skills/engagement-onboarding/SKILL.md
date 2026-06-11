---
name: engagement-onboarding
description: >
  Run the Stage-1 onboarding of a client engagement and the
  reonboard-after-rejection loop. Use this when an engagement has been
  greenlit and you need to take a target repo from cloned to first
  client-facing pull request open — the PR that installs the agency
  toolkit, captures the client account profile into the shadow, and
  speaks in the account manager (Mara) voice. Also covers what to do
  when the client rejects that PR with a change request — the account
  manager responds and the full onboarding prep re-runs against the
  same shadow. Do not use this for ongoing per-deliverable work (that
  is the cycle/build pipeline) or for generating the initial
  RFP/proposal (use rfp-response).
side: client
contract:
  kind: methodology
  inputs: []
  outputs: []
  verify:
    - skill-frontmatter
---

# Engagement Onboarding

The first thing a client sees from the agency is the **Stage-1 onboarding
pull request**. This skill governs how that PR is produced, what it must
contain, and how to handle a rejection — so the engagement opens cleanly
and the agency's memory is grounded from the very first commit.

## What onboarding produces

`loswfx engagement init <owner/repo>` takes the target from greenlit to
ready and, by default, opens the onboarding PR. In one command it:

1. Clones the target, branches, and initializes the LOSWFX workspace.
2. Bootstraps the Foreman team so the engagement is dispatch-ready.
3. Registers the engagement in the agency registry.
4. **Captures account info** — deterministically reads the client repo
   (name, README summary, detected stack) and writes the shadow
   `engagements/<client>/CLIENT-PROFILE.md`. Every role reads this to
   ground its work; product enriches the prose later.
5. **Opens the onboarding PR** — commits the vendored `.loswfx` install
   and a Mara-voiced `RESPONSE.md`, pushes the branch, and runs
   `gh pr create`. This is the client-facing confirmation that unlocks
   the team.

```sh
loswfx engagement init iksnae/xagent \
  --shadow loswf/shadow-iksnae \
  --shadow-path ~/Projects/shadow-iksnae
# → workspace staged, account profile captured, onboarding PR opened
```

Pass `--no-pr` to skip the PR (offline runs, fixtures, or when you want
to inspect the staged workspace before publishing).

## Boundaries

The onboarding PR commits:

- The vendored `.loswfx` install (to the **client** repo).
- A `RESPONSE.md` cover letter in the account manager's voice — warm,
  plain, and free of internal tooling jargon.

It does **not** commit:

- Internal reasoning, decision records, or the client profile — those
  live in the **shadow**, never the client work repo.
- Any deliverable code. Onboarding establishes the relationship and the
  install; delivery happens in subsequent cycles.

The client profile and all agency memory are **shadow-side and private**.
The seed structure of a fresh shadow comes from the shadow template — see
[`docs/SHADOW-TEMPLATE.md`](../../docs/SHADOW-TEMPLATE.md).

## Voice

Everything the client sees — the PR body, `RESPONSE.md`, and any review
replies — is in the account manager's (Mara's) voice: a single point of
contact, warm and plain, with **no internal jargon** ("capability",
"verdict", "cycle", "decompose", "sweep", "ledger", "agent", "work item",
"phase"). The internal reasoning stays in the shadow; only the outcome and
an account-manager framing surface on the client repo.

## Reonboard — open-or-refresh the onboarding PR

`loswfx engagement reonboard <owner/repo>` is the single idempotent
"ensure the onboarding PR is current" command. It covers two cases:

```sh
loswfx engagement reonboard iksnae/xagent --workdir . [--branch <b>] [--pr <n>]
```

**Backfill (no PR yet)** — for an engagement inited before the PR step
existed, or any branch without an onboarding PR: `reonboard` captures the
account profile into the shadow and **opens** the Stage-1 PR.

**Refresh (PR exists and was rejected)** — a PR has no "rejected" state: a
client rejects by **closing the PR** (usually with a comment like "please
try again"), or by leaving a `CHANGES_REQUESTED` review. Either way, do
**not** open a new PR or a new engagement. `reonboard`:

1. Reads the rejection guidance — the latest `CHANGES_REQUESTED` review
   body, or (the common case) the latest **comment** on the PR.
2. **Reopens** the PR if the client closed it — so the refresh lands on
   the same thread, not a dangling closed PR.
3. Has the account manager **respond on the PR** — acknowledging the
   feedback and quoting the client's own words back.
4. **Re-captures** the account profile into the same shadow
   `CLIENT-PROFILE.md`.
5. Refreshes the onboarding artifacts (a revised, account-manager-voiced
   `RESPONSE.md` + the `.loswfx` install) and pushes an update to the
   **same** PR branch — so the existing PR is refreshed, not duplicated.

```sh
# The client rejects by closing the PR with a comment:
gh pr close 1 --comment "please try again"
# Then re-run; the closed PR is reopened and the same shadow is reused:
loswfx engagement reonboard iksnae/xagent --workdir .
```

Each external step is best-effort: a missing `gh` or a network failure
warns but never leaves the engagement half-refreshed. Branch and PR are
auto-resolved from the checkout when not passed.

## Mara tracks the PRs she submits

Every PR the account manager opens (onboarding, and later delivery) is
recorded in her shadow ledger at
`engagements/<client>/account-manager/submitted-prs.jsonl` — purpose,
branch, URL/number, submitted date, last-known status. This is how Mara
remembers what she has in flight so she can check state and respond.

`loswfx engagement mara-review <owner/repo>` is that response loop:

1. Reads the submitted-PR ledger.
2. Checks each PR's **live state** via gh and records any change back to
   the ledger.
3. For any **onboarding PR that is now closed** (a rejection), **delegates
   to reonboard** — which reopens it, has Mara respond, re-captures, and
   refreshes. Pass `--no-delegate` to report state without acting.

```sh
loswfx engagement mara-review iksnae/xagent --workdir .
#   tracked PRs: 1
#   PR #1 (onboarding) — CLOSED
#     rejected → delegating to reonboard
```

## Acceptance → begin delivery (the handoff)

When the client **merges** the onboarding PR, the engagement is accepted
and delivery should start. A PR has no "accepted" state either — merge IS
acceptance. The seam this closes: onboarding seeds intake work items but no
*started cycle*, so the autonomous loop (`engagement loop`) finds
`no-ready-cycles` and idles.

`mara-review` handles acceptance symmetrically to rejection: a **merged**
onboarding PR → Mara **begins delivery**, bootstrapping the
ongoing-development cycle (the full canonical pipeline) so the loop has a
ready cycle.

```sh
loswfx engagement mara-review iksnae/xagent --workdir .
#   PR #1 (onboarding) — MERGED
#     accepted → beginning delivery
#     started cycle: xagent-dev (ongoing-development)
#     → engagement loop now has a ready cycle
```

The explicit primitive is `loswfx engagement start <owner/repo>`
(`workspace.BeginEngagementDelivery`) — it emits `cycle.started` for an
`ongoing-development` cycle named `<repo>-dev`. Idempotent and cheap
(ledger-only). **Running** the factory is a separate, deliberately-gated
step:

```sh
loswfx engagement loop
# or
loswfx cycle sweep --cycle xagent-dev --auto-review --auto-ship --cycle-spend-cap <N>
```

## When to use / not use

Use this skill when:

- An engagement is greenlit and needs its first client-facing PR.
- A previously-inited engagement (before the PR step existed) needs its
  onboarding PR backfilled — run `reonboard`, which opens it when none
  exists.
- The client rejected the onboarding PR and the prep must re-run.

Do not use this skill for:

- Ongoing delivery — that is the plan → build → review → ship cycle.
- Generating the opening proposal/RFP — use `rfp-response`.
- Enriching the client profile with prose/strategy — that is product's
  job in a later cycle; onboarding only captures the deterministic facts.

## Self-check

Before considering onboarding done:

- The onboarding PR is open on the client repo, `.loswfx` is installed,
  and `RESPONSE.md` reads in Mara's voice with no internal jargon.
- The shadow `engagements/<client>/CLIENT-PROFILE.md` exists with the
  client repo, a README summary, and the detected stack.
- On a rejection: the PR shows Mara's response comment AND a refreshed
  commit on the same branch; the shadow profile was re-captured.
