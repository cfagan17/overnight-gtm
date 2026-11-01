# Working in this repo (for coding agents)

## Layout and rules

- `vendor/atomic-crm/` is Atomic CRM's schema at a pinned commit. Do not edit it. To update, copy a newer `supabase/schemas/` from upstream, update `PINNED_COMMIT`, and run the tests.
- `db/migrations/` are applied in order on top of Atomic. Add new migrations; do not rewrite applied ones once a release is tagged.
- Every database function an API role can call is `security definer` with `set search_path = ''` and schema-qualified names, or `security invoker` so row-level security applies. Keep it that way. `tools/rls-audit` checks it.
- Agents must never get direct write access to ledger tables. Write policies on ledger tables require `ea_private.is_human()`. Agent writes go through functions in `0005_agent_contract.sql` that call `ea_private.agent_or_human`.
- In PL/pgSQL, `loop` is a keyword. Quote the column as `"loop"` when reading it from a record variable.
- New agent capabilities need four things: a function with checks, a grant row, a tool entry in `agents/runtime/tools.py`, and tests for both the allowed and the refused path.

## Commands

```bash
make test     # all tests; builds throwaway databases named ea_test*
make report   # regenerates docs/attack-report.md and docs/rls-audit-*.md
make demo     # builds ea_dev with the Northwind seed
```

Tests need `EA_TEST_DSN` pointing at a Postgres 16 server where the user can create databases. Never point it at a real project: the build drops and recreates databases.

## Style

Plain words in docs and comments. Say what is tested and what is not. Do not overclaim.
