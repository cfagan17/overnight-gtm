# Skill: comp credit rules

Used by the comp ops loop. Proposals only; this loop never passes level 2. Pay always has a
human signature.

## Crediting
- The AE who owns the account when the deal closes gets primary credit, unless a written
  handoff rule says otherwise.
- Overlay and SE credit follows the territory_members role (overlay) for that territory.
- Partner credit: record sourced, influenced, resold or fulfilled on deal_partners. Partner
  credit does not reduce AE credit unless the plan says so.
- Usage overage is not credited by itself; it is the trigger for a new term contract, and the
  contract is credited.

## Output
For each pay period: each closed deal, proposed credit splits with the rule that produced each,
exceptions that need a human decision, and a payout calculation. Flag anything that changed since
the last run. Never round in a rep's favor or against them; show exact numbers.
