# /factory

Use Mara's compact factory-state widget helper to surface current engagement and factory state before giving guidance.

1. Run `loswfx widget factory`
2. Show the returned widget cards first.
3. Then, in Mara voice, explain what the client or engagement human should care about right now.

Rules:

- This command is intended for an initialized LOSWFX engagement/client workspace.
- Treat this as a read-only status surface.
- Do not mutate files or run workflows unless the human explicitly asks for action after seeing the state.
- Translate factory internals into steering language rather than raw implementation detail.
