# Attack report

Generated 2026-11-01 by `scripts/attack_report.py`. Stock schema: Atomic CRM at commit `489537c369`. Hardened: the same schema plus `db/migrations`.

Each row is one attempt by one signed-in user (or a signed-out visitor) against a record they should not reach. **Blocked** means the database refused it or it touched no target rows. Run on Postgres 16 with `db/test-shim/supabase_shim.sql` standing in for Supabase's auth layer.

| Attempt | Actor | Stock Atomic | Hardened |
| --- | --- | --- | --- |
| Rep reads another territory's deal | West AE | **Allowed** (returned 1 row(s)) | Blocked (no rows returned) |
| Rep reads another territory's contacts | West AE | **Allowed** (returned 1 row(s)) | Blocked (no rows returned) |
| Rep reads another rep's call notes | West AE | **Allowed** (returned 1 row(s)) | Blocked (no rows returned) |
| Rep changes another rep's deal amount | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep reassigns another rep's deal to herself | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep deletes another rep's deal | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep deletes another rep's account (cascades to contacts and deals) | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep rewrites another rep's call note | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep deletes another rep's tasks | West AE | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Rep adds a deal to another rep's account (inflating that territory's pipeline) | West AE | **Allowed** (1 row(s) changed) | Blocked (refused: new row violates row-level security policy for table "deals") |
| Read-only finance user changes a deal | Read-only user | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Agent account edits a deal stage directly, with no decision or evidence | Agent | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Agent account deletes a deal directly | Agent | **Allowed** (1 row(s) changed) | Blocked (0 rows changed) |
| Agent account reads a deal outside its scope | Agent | **Allowed** (returned 1 row(s)) | Blocked (no rows returned) |
| Signed-out visitor reads accounts | Signed out | Blocked (no rows returned) | Blocked (refused: permission denied for table companies) |

Stock Atomic allowed 14 of 15 attempts. The hardened schema allowed 0.

Stock Atomic is a good template that is honest about its scope: it is built for a small team where everyone may see and change everything. The point of this report is what changes when that assumption stops holding, and when AI agents connect as users.

See also `docs/rls-audit-stock-atomic.md` and `docs/rls-audit-hardened.md`, produced by `tools/rls-audit` on the same two databases.
