# Skill: health score

Used by the post-sale health loop.

## Signals
- Usage trend against the contract (growing, flat, declining), and breadth (features, teams).
- Support: ticket volume and severity trend, unresolved escalations.
- Relationship: champion still there and active, executive engagement, open commitments kept.
- Commercial: renewal date, payment issues, contract headroom (usage near or over commitment).

## Output
A score from 0 to 100 with the three biggest drivers and their evidence ids, a churn risk flag
when the score drops more than 15 points in 30 days or the champion leaves, and an expansion flag
when usage passes 80% of contracted volume. Usage overage is the trigger to propose a new term
contract, not a bill.

## Promotion metric
Churn flagged at least 90 days ahead, as a share of all churn. Measured each quarter.
