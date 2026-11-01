# earned-autonomy

**An operating layer for GTM teams where AI agents do more of the work, and earn the right to do it.**

Most AI sales tools bolt a feature onto a CRM built for people typing into forms. This repo starts from a different question. If a capable model sits at the center of go-to-market, reading every account, conversation and partner signal and doing as much of the work as it reliably can, what does the system underneath need to look like?

The answer here is concrete and runs as code:

1. **A ledger (Layer 1)** for the facts that forecasts, comp and board numbers come from: accounts, contacts, deals, lines, contracts, territories, partners, weekly forecast snapshots.
2. **A control plane (Layer 2)** enforced inside Postgres. Visibility follows ownership, management chain and territory. Agents have their own identities, scoped grants, and no direct write access to the ledger. Changes to ledger and governance tables are audited.
3. **New primitives** that store *why*, not just *what*: evidence, strategies, experiments, decisions, policies, commitments, plus runs and skills that record how each agent worked.
4. **Twelve loops**, from account planning and conversation capture to territory design and comp ops, each starting at a low autonomy level.
5. **A promotion review.** A loop moves up a level only when its record clears a bar: reviewed decisions, replay evals, holdout experiments, and zero policy violations. A new model release becomes a promotion review, not a rewrite.

![System diagram](docs/system-diagram.png)

## What has been measured

Built on [Atomic CRM](https://github.com/marmelab/atomic-crm) (MIT, Supabase), whose real schema is vendored at a pinned commit. The same 15 attacks were run against stock Atomic and against Atomic plus these migrations ([full report](docs/attack-report.md)):

| | Stock Atomic | With earned-autonomy |
| --- | --- | --- |
| Attacks allowed (a rep reading, editing or deleting another territory's records, a read-only user editing, an agent writing directly) | 14 of 15 | 0 of 15 |
| `tools/rls-audit` findings, high | 33 | 0 |
| `tools/rls-audit` findings, medium (after review) | 28 | 0 |

Stock Atomic is a good template that is honest about its scope: a small team where everyone may see and change everything. The report shows what changes when that stops being true, and when AI agents connect as users.

Before publishing, an independent adversarial review tried to break the hardened schema and found real holes, including two ways an agent could change records outside its scope. All confirmed findings are fixed and each has a regression test. The [review write-up](docs/review-2026-11-01.md) lists what was found, what changed, and what is still open.

The test suite (73 tests) also covers the agent contract: agents cannot act outside their scope, cite evidence they cannot see, state weak evidence as fact in a plan, change a field without a decision citing strong evidence, touch a do-not-contact person or a partner-owned account, raise their own autonomy, or act on accounts held out of an experiment. See [STATUS.md](STATUS.md) for exactly what is tested and what is design only.

## Three ways to use it

| Mode | For | The ledger lives in |
| --- | --- | --- |
| Greenfield | A startup with a GTM engineer and no CRM worth keeping | An Atomic CRM fork on Supabase |
| Salesforce sidecar | Growth and enterprise companies | Salesforce. Supabase holds the primitives and a thin id/owner mirror. Agent changes go back through one integration user with a narrow permission set |
| HubSpot sidecar | SMB and mid-market | HubSpot, the same way |

Not sure which, or whether at all? Run `tools/fit-assessment` (or point your own AI at [EVALUATE.md](EVALUATE.md)). For a small team without a GTM engineer, the honest answer is usually to buy a maintained AI-native CRM and borrow the method.

## Try it

Needs Postgres 16 and Python 3.11+. No Supabase account needed for the tests: a small shim stands in for Supabase's auth layer.

```bash
pip install -r requirements.txt
export EA_TEST_DSN="postgresql://postgres@localhost:5432/postgres"   # a Postgres you can create databases on
make test           # builds fresh databases and runs all tests
make report         # regenerates docs/attack-report.md and the rls-audit reports
make demo           # a seeded demo database (fictional company "Northwind Data")
```

Run a loop with a live model (any Anthropic model id):

```bash
export ANTHROPIC_API_KEY=...
python agents/runtime/runner.py --loop account_program --input '{"company_id": 1}' \
  --dsn "$DEMO_DSN" --agent-uid 00000000-0000-0000-0000-000000000102 --model <model-id>
```

Audit your own Supabase project (read-only by default):

```bash
python tools/rls-audit/rls_audit.py --dsn "$SUPABASE_DB_URL"
```

Deploying on a real Supabase project: [docs/deploying.md](docs/deploying.md).

## What is in the repo

| Path | What |
| --- | --- |
| `db/migrations/` | Eight migrations: ledger, control plane, primitives, runtime, agent contract, promotion, sidecar, final grants |
| `agents/loops/` | Twelve loop definitions with prompts, tools, starting and maximum levels, promotion metrics |
| `agents/skills/` | Versioned methodology the agents load: evidence rules, MEDDPICC, stages, account plans, territories, comp credit, partners, health, forecasting |
| `agents/runtime/` | The runner (live model or scripted), tool definitions, transports for direct Postgres and Supabase REST |
| `agents/hooks/` | A Claude Code capture hook that records each tool call to `run_events` |
| `evals/` | Offline replay harness, deterministic scorers, starter eval sets (synthetic, labeled as such) |
| `tools/rls-audit/` | Standalone row-level security checker for any Supabase project |
| `tools/fit-assessment/` | Should you use this, and in which mode |
| `sidecars/` | Salesforce and HubSpot ingest and writeback, plus Salesforce metadata (custom fields, permission set) |
| `examples/` | Scripted runs, and partner intelligence on a public snapshot of Supabase's integration listings |
| `docs/` | Design, attack report, audit reports, deployment |
| `vendor/atomic-crm/` | Atomic CRM's schema at a pinned commit, MIT licensed |

## Credits

- [Atomic CRM](https://github.com/marmelab/atomic-crm) by Marmelab is the base. Its schema is vendored unchanged under its MIT license.
- Several agent-governance ideas come from [Comp AI CRM](https://github.com/trycompai/crm): evidence strength priced by kind rather than by the model's own confidence, per-agent tool grants, and "the CRM is where the agent keeps its notes."
- Linking an agent session to the change it produced follows the pattern [Entire](https://rywalker.com/research/entire) uses for code.

## License

MIT. See [LICENSE](LICENSE).

Built by Cameron Fagan, with Claude. I have spent ten years building GTM systems (partner operations, territories, forecasting, comp) at Salesforce, HashiCorp and Aviatrix. I wrote this with AI and checked it with tests rather than by reading every line myself, which is also how I think much GTM software will be built from here.
