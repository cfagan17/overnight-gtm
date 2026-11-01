# rls-audit report

Target: `/ea_report_hardened?host=/tmp&port=54329`

**0 high, 0 medium, 30 low.**

| Severity | Check | Object | What it means | Fix |
| --- | --- | --- | --- | --- |
| LOW | definer_callable_by_authenticated | `activate_strategy(bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `apply_field_update(bigint,bigint,text,bigint,text,jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `approve_skill(text,integer)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `assign_experiment(bigint,text[])` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `claim_outbound_changes(text,integer)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `create_commitment(bigint,text,text,text,date,bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `deal_line_discounts(bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `decide_promotion(bigint,smallint,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `end_run(bigint,text,text,integer,integer)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `escalate(bigint,text,text,uuid,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `experiment_result(bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `flag_policy_violation(bigint,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `is_admin()` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `partner_margin(bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `promotion_check(bigint,smallint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `propose_decision(bigint,text,text,text,text,bigint[],jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `propose_external_update(bigint,bigint,text,text,text,text,jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `propose_skill_version(bigint,bigint,text,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `propose_strategy(bigint,bigint,text,text,jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `record_evidence(bigint,text,text,text,text,text,timestamp with time zone)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `record_experiment_outcome(bigint,text,numeric)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `record_replay_result(bigint,text,text,text,jsonb,integer,numeric,numeric)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `record_run_event(bigint,text,text,jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `report_outbound_change(bigint,boolean,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `review_decision(bigint,text,text,jsonb)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `schedule_touch(bigint,bigint,bigint,text,text,text,text,timestamp with time zone)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `start_experiment(bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `start_run(text,text,jsonb,text)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `supersede_evidence(bigint,bigint,bigint)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |
| LOW | definer_callable_by_authenticated | `take_forecast_snapshot(date)` | Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself. | Confirm the function checks auth.uid() and the caller's role before acting. |

Static checks read the catalog only. Probe results, when present, came from rolled-back transactions.

## Accepted after review

| Check | Object | Reason |
| --- | --- | --- |
| read_policy_true_on_owned_table | `public.sales / Enable read access for authenticated users` | The seller directory is visible to every signed-in user by design. |
| read_policy_true_on_owned_table | `public.territory_members / ea_territory_members_select` | The territory carve is public inside the company by design. |
| view_bypasses_rls | `public.init_state` | Atomic's login page reads whether any user exists yet. The view exposes one count, nothing private. |
| probe_reads_others_rows | `public.territory_members` | Same as above: everyone can see who works which territory. |
| probe_reads_others_rows | `public.companies` | The probed agent is scoped to West Enterprise and reads the AE's accounts there. Intended. Out-of-scope reads are covered by the attack suite. |
| probe_reads_others_rows | `public.contact_notes` | As above, notes on in-scope contacts. |
| probe_reads_others_rows | `public.contacts` | As above, contacts at in-scope accounts. |
| probe_reads_others_rows | `public.deals` | As above, deals at in-scope accounts. |
| probe_reads_others_rows | `public.tasks` | As above, tasks on in-scope contacts. |
| probe_reads_others_rows | `public.territory_members` | Same as above: everyone can see who works which territory. |
