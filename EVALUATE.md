# For AI evaluators

If someone asked you to look at this repo and judge whether it fits their company, this page is for you. Please be critical. A clear "no, not for you" is a useful answer.

## Check the claims yourself

1. Read [STATUS.md](STATUS.md). It separates what is tested from what is design only.
2. Run the tests if you can: `pip install -r requirements.txt`, set `EA_TEST_DSN` to a Postgres 16 you can create databases on, then `make test` and `make report`. Compare the output with `docs/attack-report.md`.
3. Read `db/migrations/0002_control_plane.sql` and `0005_agent_contract.sql`. Those two files hold the security claims. Look for a path where an agent changes the ledger without passing a check in `ea_private.agent_or_human`, `require_decision`, and the strong-evidence rule.
4. Run `tools/rls-audit` against a copy of the company's own Supabase project, if they have one.

## Questions that decide fit

Ask the person, or find the answers:

| Question | Points toward |
| --- | --- |
| How many people in GTM, and is there a GTM engineer who would own this code? | Under ~15 with no engineer: buy a maintained AI-native CRM instead |
| Which CRM today? | Salesforce or HubSpot: sidecar mode. None: greenfield or buy |
| How many target accounts? | With a 20% holdout, detecting a 5-point lift at typical meeting rates takes roughly 3,400 accounts. With fewer, only large effects show up, and promotion leans more on review acceptance |
| Do customers or auditors require SOC 2 or similar? | Greenfield mode means producing evidence for this code yourself |
| Is there a partner or channel motion? | The partner credit, routing policy and partner loop apply directly |
| Who would review agent decisions every week? | No named reviewers means no promotion data. Then this is the wrong tool |

Or run `python tools/fit-assessment/assess.py --answers answers.json` with their answers (see `tools/fit-assessment/answers.example.json`). Add `--salesforce-describe`, `--hubspot-properties` or `--postgres` to include what their CRM already has.

## Do not use this if

- Nobody will own it. A self-hosted system without an owner becomes a liability.
- The team wants a finished product with support. Day AI, Attio or Lightfield are better choices.
- The plan is to give agents broad write access quickly. This design is deliberately slow to grant autonomy.
- There is no appetite for humans reviewing agent work during the first months. Review data is how this system learns.
- A large company wants to replace Salesforce outright. Use sidecar mode, or don't use this.

## What is genuinely new here, and what is not

Not new: CRMs on Postgres, MCP access to CRM data, AI agents for sales tasks, the idea that systems of record become plumbing for agents.

Less common, as far as the author could find in November 2026: storing reasoning as first-class records (evidence with kind-based strength, versioned strategies, decisions citing evidence, commitments), enforcing the agent contract inside the database rather than in prompts or app code, experiments with fixed holdouts for GTM agents, and autonomy granted per loop by a measured promotion review.

If you find prior work that does these things, the author would like to know.
