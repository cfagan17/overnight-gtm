# Skill: market model

Used by the market model loop, weekly.

## Job
Keep a score for every account against the ideal customer profile, and keep the profile honest.

## Method
1. Build the profile from closed-won and closed-lost deals: which attributes (segment, industry,
   tech used, product usage signals, size) separate wins from losses. Use only attributes that
   were known before the deal started, or the model will learn from the outcome.
2. Score each account. Record the score and its top drivers as evidence of kind `inferred`
   (weak), because a score is a conclusion, not an observation.
3. Report how the top-scored decile has performed against the rest, on holdout accounts only.

## Rules
- Never change ownership or territory based on a score. Scores feed the territory loop's proposals.
- Say when data is too thin to score (fewer than about 30 won deals in a segment).
