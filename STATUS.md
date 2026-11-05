# Status: what is tested and what is design only

Updated 2026-11-05. "Tested" means covered by `make test` on Postgres 16 with the Supabase shim in `db/test-shim/`. The suite has also run against a hosted Supabase project (see `docs/supabase-hosted-check.md`). Nothing here has run against a Salesforce org or a HubSpot portal yet.

## Tested

| Area | What the tests show | Where |
| --- | --- | --- |
| Compatibility with Atomic CRM | Atomic's real schema (pinned commit) loads, then all nine migrations apply on top | `scripts/build_db.py` |
| Record visibility | Owner and read-only see everything; managers see their chain; reps see their own records and their territory; agents see only their grant scope | `tests/test_control_plane.py` |
| Write boundaries | Reps edit their own records and archive rather than delete; managers edit and delete within their chain only; records cannot be added to or moved onto accounts the caller cannot edit; only owners change territory assignments | `tests/test_control_plane.py`, `tests/test_review_regressions.py` |
| Field masking | Discount and partner margin are not selectable by API roles, and never enter the audit log; only owners, managers and the partner manager read them through functions | `tests/test_control_plane.py`, `tests/test_review_regressions.py` |
| Audit | Every ledger change is logged with principal and kind; reps cannot read or alter the log; setting a session variable cannot forge agent attribution | `tests/test_control_plane.py` |
| Shared attack suite | 15 attacks: 14 succeed on stock Atomic, 0 on the hardened schema | `tests/test_attacks.py`, `docs/attack-report.md` |
| Independent review findings | Each confirmed finding from two review passes is reproduced and refused | `tests/test_review_regressions.py`, `docs/review-2026-11-01.md` |
| rls-audit tool | Finds the stock gaps (33 high); passes the hardened schema with 0 high and 0 medium after documented review | `tests/test_rls_audit.py`, `docs/rls-audit-*.md` |
| Agent contract | Runs belong to one agent; tools need grants; scope limits reads; evidence strength comes from its kind and source, and evidence is append-only, even for superusers; decisions must cite visible evidence; plans cannot cite evidence their decision does not; internal helpers cannot be called directly | `tests/test_agent_contract.py`, `tests/test_review_regressions.py` |
| Autonomy levels | Level 1 field updates refused; level 2 queues for the record owner and applies on approval, attributed to the decision and approver; level 3 applies directly; weak-only evidence, non-allowlisted fields, mismatched payloads and reused decisions are refused | `tests/test_agent_contract.py` |
| Outreach policies | Pending approval at level 2; blocked for do-not-contact, a fourth touch in 14 days, a partner-sourced account without the partner as sender, and agent SMS; a touch sent as a person or partner always waits for them | `tests/test_agent_contract.py`, `tests/test_review_regressions.py` |
| Holdouts | Assignment is deterministic and fixed once started; a running experiment's definition is frozen and outcomes are written once; strategies for held-out accounts are recorded but cannot be activated | `tests/test_agent_contract.py`, `tests/test_review_regressions.py` |
| Promotion | Agents cannot raise their own level; `decide_promotion` has no override; changes to the bar are audited and recorded with each promotion; a loop that clears the bar is promoted; one confirmed violation demotes; comp, territory and operating design loops are capped at level 2 by a constraint, and a loop name cannot change | `tests/test_agent_contract.py`, `tests/test_review_regressions.py` |
| Experiment math | The design doc's worked example (48 of 320 vs 8 of 80) gives the stated range and "inconclusive" | `tests/test_agent_contract.py` |
| Skills | Agents propose new versions through a decision; only owners approve | `tests/test_agent_contract.py` |
| Runner | All 12 loop definitions load with known tools, and their prompts are plain English with no tool names; scripted runs complete end to end over the real database functions, recording every event | `tests/test_runtime.py`, `tests/test_loop_prompts.py` |
| Replay evals | Scorers reward the right behavior and penalize stating weak evidence as fact, wrong sender and uncited evidence | `tests/test_replay.py` |
| Sidecars (logic only) | Ingest fills the visibility mirror; a level 2 Salesforce change waits for the owner, is refused for a non-owner, and is written back with its decision id; HubSpot request shapes; only the worker can claim changes | `tests/test_sidecars.py` (fake HTTP sessions) |
| Ask-your-data queries | Each starter query in `examples/queries/` runs as an owner on the seeded database | `tests/test_queries.py` |
| Hosted Supabase | Installs cleanly on a real project (Postgres 17), and the suite passes against it: 88 passed, 9 skipped (the skipped tests need a scratch database). The first run found a default-grant gap the shim did not model, now fixed and modeled | `docs/supabase-hosted-check.md` |
| Console data paths | Prompt versions: only owners propose and approve, agents read only their own loop's approved prompt, and the runner uses it. Insight views respect each person's access. The review queue shows only what each person may approve; reps cannot sign off comp, territory or process decisions, even on their own deals. Loop activity shows that loops ran without exposing run rows | `tests/test_console.py`, `tests/test_runtime.py` |
| Slack | The digest goes to each mapped person with only what they may review; a click acts as the mapped person, so a rep without access changes nothing; forged and replayed requests are refused; signed-in users cannot call the Slack functions | `tests/test_slack.py`, `tests/test_console.py` |
| Demo history | The generator loads, approves all 12 prompts and leaves each demo person a queue | `tests/test_demo.py` |
| Fit assessment | Recommendations for small teams, Salesforce companies and greenfield builds; reading Salesforce describe output and a Postgres schema | `tests/test_fit_assessment.py` |

## Design only, not yet tested

| Area | Why not yet | What would test it |
| --- | --- | --- |
| Loop quality with a live model | One live run on demo data is documented in `examples/live-run/`. One run shows the loop works, not how often it is right | Run loops on real accounts, record reviews, watch `loop_review_stats` |
| Eval sets | The starter sets are synthetic and small (5 and 6 cases) | Replace with about 200 human-verified past cases per loop |
| Promotion thresholds (80%, 95%) | Starting guesses | The first 100 real reviews per loop |
| Salesforce and HubSpot against real systems | No test org or portal here | A Salesforce scratch org and a HubSpot developer portal |
| Row-level security at scale | Seed has 24 accounts | 1M deals and a 5-level manager chain; measure query time |
| Partner intelligence on public data | The snapshot is partial (37 of 119 listings rendered) and the loop needs a live model | Re-capture the listings, run `examples/partner-intelligence-public/run.py` |
| Console in the browser | Checked by screenshots as five people against the hosted demo, not by automated browser tests | Playwright tests per role |
| Slack against a real workspace | The digest and handler are tested against the database with signed requests, not a live Slack app | Install the app in a test workspace |
| Atomic's UI on the hardened schema | Tests cover the database, not the React app | Run the Atomic app against the hardened database and click through as each role |

## Known limits

- See "Still open" in `docs/review-2026-11-01.md`: helper functions that can reveal a record's owner and territory id, self-reported run metadata, trust in agent transcription when a source allows agent writes, and Atomic's open storage policies.
- Supabase's SOC 2 covers its infrastructure, not this application. Anyone running greenfield mode owns the evidence for this code.
- In HubSpot sidecar mode, deals and contacts get visibility from their owner only; territory comes from the company property.
- One reviewer measures one person's taste. Promotion is more credible with two or more reviewers per loop.
