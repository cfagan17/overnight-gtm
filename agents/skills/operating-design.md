# Skill: operating design

Used by the operating design loop, quarterly. This loop proposes changes to how the GTM system
works. It never passes level 2: changes to process are human decisions.

## Inputs
Stage conversion and time-in-stage, review outcomes by loop (what humans keep editing or
rejecting), experiment results, forecast accuracy, and the current skills.

## What it may propose
- New exit criteria for a stage, as a new version of the stages skill.
- A methodology mix by segment (for example MEDDPICC fields required above a deal size, a
  lighter product-led motion below it).
- A change to the split of work between humans and agents in a segment, with the evidence.
- A new experiment to settle a question the data cannot answer yet.

## Rules
- Every proposal cites data and says what result would prove it wrong.
- Prefer one change at a time, so its effect can be measured.
- Skill changes go through `propose_skill_version`; an owner approves them.
