# Skill: forecast method

Used by the forecast loop. The forecast call stays with the sales leader. This loop produces an
independent call with reasons, so the leader can pressure-test the bottoms-up number.

## Inputs
Weekly forecast snapshots, current deals with stage and category, evidence on each commit and
best-case deal, historical stage-to-close conversion and slippage by segment.

## Method
1. Start from history: for each segment, the share of pipeline at each stage that historically
   closed in-quarter, and how often committed deals slipped.
2. Adjust deal by deal only on evidence: paper process started, economic buyer engaged, or the
   opposite (silence, a new stakeholder, a pushed date).
3. Produce: a number per segment, a low and high range, the five deals that move the number most,
   and for each the evidence behind your view.
4. Compare with last week's snapshot. Explain every change over 10% in one line.

## Rules
- Never change forecast_category on a deal. That is the rep's and manager's call.
- Report your accuracy honestly: each quarter, compare your call and the human call with actuals.
  That comparison is this loop's promotion metric.
