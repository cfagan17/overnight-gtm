# Skill: deal inspection

Used by the deal inspection loop, daily on open deals.

## Look for
- A late-stage deal with MEDDPICC gaps (economic buyer or paper process unknown).
- Silence: no strong evidence in 14 days on a commit deal, 21 days on best case.
- A close date pushed twice.
- A new stakeholder late in the cycle, or the champion going quiet.
- A deal whose stage is ahead of its evidence (see the stages skill).

## Output
For each flagged deal: the risk in one sentence, the evidence ids, and one proposed next step for
the owner. Rank by amount times risk. Propose at most five a day per rep, so the list gets read.

## Promotion metric
Of deals that slipped or were lost, the share this loop flagged at least 30 days before.
