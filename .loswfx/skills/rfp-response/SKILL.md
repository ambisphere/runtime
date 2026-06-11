---
name: rfp-response
description: Respond to a client's Request For Proposal (RFP) with a coherent multi-document proposal that demonstrates LOSWF Agency read the RFP, has a position on the client's specific problem, and proposes concrete deliverables matching the RFP's stated expectations. Use this skill when a client has published an RFP and LOSWF is invited to respond. Output is a set of markdown documents under proposals/<client>/ covering cover-letter, approach-by-phase, portfolio-and-experience, engagement-model, and a README index. Do not use this skill for unsolicited outreach (no RFP) or for engagement renewals (no fresh RFP) — those have their own shapes.
side: client
# Empirically validated in the iksnae/gitugh SUT round
# (2026-05-26): gpt-oss-120b reliably bails on this skill's
# dense multi-file framing; glm-4.7 engages cleanly. Operators
# can override via RunOptions.Model when they need a different
# model.
model: z-ai/glm-4.7
contract:
  kind: deliverable
  inputs:
    - kind: layer-3
      path: clients/{repo}/**
      required: true
  outputs:
    - path: proposals/{repo}/rfp-response.md
      required: true
  verify:
    - truthful-status
    - skill-frontmatter
---

# RFP Response

This skill drives the LOSWF Agency through a structured response to a
client RFP. The work product is a set of markdown documents that
collectively form the proposal.

## Purpose and boundaries

The response demonstrates three things in this order, in every document:

1. **You read the RFP.** Reference it by section. Quote the client's
   actual language for design principles, aversions, and deliverable
   categories.
2. **You have a position on the client's specific problem.** Not
   generic "we deliver quality." Concrete: how would you visualize
   their workflow graph? How would you avoid the specific aversions
   the RFP names? What's your view on their reference points?
3. **You propose deliverable artifacts that match what the RFP asks
   for.** Echo the RFP's deliverable expectations specifically.

This skill does **not** produce:

- Generic agency self-portrait documents (the cover letter is one
  paragraph of identity, then the rest is RFP-engagement)
- Fabricated past clients or invented case studies
- Marketing-grade superlatives ("transform", "revolutionize", "world-class")
- Diagrams or design artifacts (those are deliverables of a *won*
  engagement, not the proposal)

## Inputs

Required:

- **RFP document** — a markdown or PDF file the client published.
  Read it with the `read_file` tool before drafting anything.

Optional:

- **Client name** — used in the output path. Defaults to the RFP
  document's parent directory name.

## Output

Five markdown files under `proposals/<client>/`:

1. `00-cover-letter.md` — opens with "We read your RFP" or equivalent
   phrasing. One paragraph of agency identity. Then a paragraph on
   each of the RFP's named design principles. Then a paragraph
   addressing the RFP's explicit aversions (what to avoid). Close
   with one sentence on engagement model preference.
2. `01-approach-by-phase.md` — for each phase the RFP defines:
   (a) quote the RFP's stated deliverables for the phase, (b) describe
   how LOSWF Agency would execute that phase, (c) name specifically
   what LOSWF would deliver to the client.
3. `02-portfolio-and-experience.md` — address each "Desired Experience"
   category the RFP lists. For each one LOSWF can genuinely claim:
   a short capability statement (no fabricated past clients).
4. `03-engagement-model.md` — pick one or two of the RFP's listed
   engagement options as preferred, explain why that shape fits the
   client's specific situation. Address each "Proposal Requirements"
   bullet line by line.
5. `README.md` — index linking to the four documents above with a
   one-line summary each that mentions the client by name.

## Workflow

### Step 1: Read the RFP

Use `read_file` on the RFP document. Do not draft anything yet. Build
a mental list of:

- The phases / sections the RFP defines
- The principles or values the RFP explicitly states
- The aversions the RFP explicitly names (what to avoid)
- The "Desired Experience" categories the RFP lists
- The "Engagement Model" options the RFP offers
- The "Proposal Requirements" the RFP demands

### Step 2: Write the cover letter

Open with the literal phrase "We read your RFP" or "we read the RFP".
This is the signal to the client that this is not a template response.
Then engage with the RFP's specific content.

### Step 3: Write the approach-by-phase document

One section per RFP phase. Each section opens by quoting what the RFP
asks for in that phase, then proposes LOSWF's execution.

### Step 4: Write the portfolio and engagement model

These are the two documents most prone to drift into agency-self-portrait
mode. Discipline: every claim about LOSWF must tie back to a category
or option the RFP listed.

### Step 5: Write the README

The README is the entry point. Each document gets a one-line summary
that mentions the client by name.

### Step 6: Self-check

Verify before completion:

- All five files exist
- The cover letter contains "We read your RFP" or "we read the RFP"
- Each document mentions the client by name at least once
- No document contains a fabricated past client name
- No document uses marketing superlatives ("transform", "revolutionize",
  "world-class", "best-in-class", "cutting-edge")
- The RFP is referenced by section or quote at least three times across
  the documents

## Failure modes to avoid

- **Agency-headline framing.** "LOSWF is an autonomous software factory..."
  is what the README is *for* internally; in an RFP response the lead is
  always the client's problem.
- **Inventing a name for LOSWF.** The agency name is "LOSWF Agency."
  Not "Local Omniscient System for Workflows" or any other expansion.
- **Leaking work-item-id or debug names into the content.** The RFP is
  whatever the client called it ("Gitugh Product Design RFP"), not
  "RFP v3" or "RFP target".
- **Empty engagement-model document.** Every RFP names engagement
  options. Pick one or two and defend the choice with reference to the
  client's specific situation.

## Verification

The response is complete when:

- All five markdown files exist under `proposals/<client>/`
- The README references the other four files
- The cover letter contains "We read your RFP" or "we read the RFP"
- Each document references the RFP at least once (grep for "RFP" must
  match in all five files)
- No document contains "Local Omniscient System" or similar invented
  expansions
