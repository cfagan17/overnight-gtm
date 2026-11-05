# A live run: account program on Acme Orchards

One real run of the account program loop with Claude (`claude-opus-5-5`), on the Northwind demo
data. This was not scripted. The model chose every tool call.

## Setup

- Database: `db/seed/seed.sql` plus `examples/demo/acme_signals.sql`. That file adds seven
  fictional signals for Acme Orchards, written as if by the capture integration, and the last
  plan version, which the rep (Maya) had edited to make herself the sender.
- Loop: `agents/loops/account_program/` at prompt v2, with the evidence, account-plan and
  MEDDPICC skills.
- Agent: the account-program agent at autonomy level 1 (suggest). Its grant covers West Enterprise only.
- Ran on Postgres 16 with the test shim. 34,292 input and 3,110 output tokens, about 30 seconds.

```bash
python agents/runtime/runner.py --loop account_program --input '{"company_id": 1}' \
  --dsn "$DEMO_DSN" --agent-uid 00000000-0000-0000-0000-000000000102 --model claude-opus-5-5
```

## What it did

Seven tool calls, all logged to `run_events`:

1. Read the account context: contacts, the open deal, seven evidence rows, and the v1 plan with Maya's edit.
2. Checked contact policies for Priya Shah, Jordan Lee and Casey Ruiz.
3. Searched the deal's evidence (nothing new).
4. Filed one decision citing all seven evidence rows.
5. Proposed strategy v2.

## What is worth noticing

- **It learned from the review.** Maya's edit to v1 said "Anything to Acme comes from me, not the
  agent." The new plan makes Maya the sender and says why. The prompt tells the loop to follow
  the last edit unless new evidence says otherwise.
- **It caught a problem nobody had flagged.** The deal's close date is eight days out, but
  procurement said a multi-year deal needs about three weeks. The plan lists this as the first
  risk and asks the rep to confirm the term and re-date the deal.
- **It treated weak evidence as weak.** The careers page post about data platform hiring is a
  `web_page` (weak), so the plan uses it only as a question to ask, not as a claim.
- **It did not overclaim.** Priya is called a possible champion until she acts, and the plan
  says there is no evidence yet of who approves the spend.

`output.json` has the decision and the full v2 plan. `transcript.json` has the system prompt and
every model turn, tool call and tool result.

One run shows the loop can do the work. It does not show how often it does it well. That is
what the review record and replay evals are for (see STATUS.md).
