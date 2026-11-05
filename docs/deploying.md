# Deploying on Supabase

Tested on a hosted Supabase project on 2026-11-05 (see `docs/supabase-hosted-check.md`). Use a Supabase branch or a spare project first, run the tests against it, then promote.

## Quick start on a fresh project

```bash
pip install -r requirements.txt
export SUPABASE_DB_URL="postgresql://postgres.<ref>:<db password>@aws-0-<region>.pooler.supabase.com:5432/postgres"   # Connect > Direct > Session pooler
python scripts/install_hosted.py --dsn "$SUPABASE_DB_URL" --seed --demo     # Atomic + migrations + Northwind demo data
EA_HOSTED_DSN="$SUPABASE_DB_URL" pytest tests                                  # runs in rolled-back transactions
```

The connection string needs the database password (Project Settings > Database), not your Supabase account password. Percent-encode any symbols in it.

## Greenfield (Atomic CRM fork)

1. Fork [Atomic CRM](https://github.com/marmelab/atomic-crm) and deploy it as its docs describe (`make supabase-remote-init`).
2. Copy `db/migrations/*.sql` into the fork's `supabase/migrations/` with timestamps after Atomic's latest, keeping their order. Do not copy `db/test-shim/`. Supabase already has everything the shim fakes.
3. `supabase db push`.
4. Fill `public.principals` for your people: role and manager for each. Until you do, Atomic's administrator flag maps to owner and everyone else to rep.
5. Load skills: `python scripts/load_skills.py --dsn "$DATABASE_URL" --owner-uid <your auth user id>`.
6. For each loop you turn on:
   - Create an agent auth user with app metadata `{"ea_kind": "agent"}` (Admin API: `auth.admin.createUser({ email, app_metadata: { ea_kind: "agent" } })`). Atomic requires an invitation row first (`public.user_invitations`).
   - Insert its `principals` row (`kind = 'agent'`, `role = 'agent'`, `agent_definition_id`).
   - Insert `agent_grants` rows for the loop's tools, with a scope (`{"all": true}` or `{"territory_ids": [..]}`) and `approved_at`.
   - Mint a JWT for the agent user and store it where the runner runs.
7. Schedule `select public.take_forecast_snapshot();` weekly with `pg_cron`.
8. Run `tools/rls-audit/rls_audit.py --dsn "$DATABASE_URL"` and review every finding.

## Salesforce sidecar

1. Create a Supabase project. Apply Atomic's schema too, because the primitives reference its `sales` table as the seller directory, then all migrations.
2. Deploy `sidecars/salesforce/metadata` (`sf project deploy start --manifest package.xml`). Assign `EA_Agent_Writer` to one integration user and nothing else.
3. Fill `sidecar_user_map` (Salesforce user id to seller) and `sidecar_territory_map` (territory key to territory).
4. Schedule `sf_sidecar.py ingest` (every few minutes, with `--since` the last run) and `sf_sidecar.py writeback`.
5. Give conversation capture and deal inspection the `propose_external_update` tool instead of `apply_field_update`.

## HubSpot sidecar

The same, with `sidecars/hubspot/`. Create the properties in `properties.json`, use a private app token scoped to the allowlisted properties, and fill the maps with HubSpot owner ids.

## Running loops

Live, over Supabase REST, as the agent:

```bash
python agents/runtime/runner.py --loop account_program --input '{"company_id": 42}' \
  --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" --jwt "$ACCOUNT_PROGRAM_AGENT_JWT" \
  --model <anthropic model id>
```

Review queue for humans: decisions with `status in ('proposed','queued')` on records the reviewer can see, approved or edited with `public.review_decision(...)`. Atomic's UI does not have a review screen yet; that is the first UI work to do.
