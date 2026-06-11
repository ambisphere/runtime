# /queue

Use Mara's queue-state widget helper to surface current work pressure, approvals, and attention items.

1. Run `loswfx widget queue`
2. Show the returned widget cards first.
3. Then, in Mara voice, summarize what should be handled next, what is blocked, and what can be delegated into the factory.

Rules:

- This command is intended for an initialized LOSWFX engagement/client workspace.
- Keep the output read-only unless the human asks Mara to take the next step.
- Prioritize approvals, failures, and items needing steering.
- Explain the queue in human terms, not just factory terms.
