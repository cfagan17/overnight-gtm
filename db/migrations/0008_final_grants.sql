-- 0008 Final grants on ea_private
--
-- Earlier migrations granted every ea_private function to signed-in users. That was too
-- wide: some helpers change data or reveal facts when called directly (an independent
-- review showed execute_field_update could be called with a forged decision). Now API
-- roles may run only the helpers that row-level security policies and security-invoker
-- read functions call. Everything else is reachable only through the public contract
-- functions, which run as their owner.

revoke execute on all functions in schema ea_private from public, anon, authenticated;

do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'ea_private' and p.proname in (
      -- identity and role
      'current_role_name','current_kind','current_sales_id','current_agent_definition_id','is_human',
      -- visibility used by policies
      'manages','in_my_territory','agent_scope_allows','can_see','can_edit','can_delete',
      'company_owner_territory','deal_owner_territory','contact_owner_territory',
      'can_see_company','can_see_deal','can_see_contact','can_edit_deal','can_edit_contact','can_see_subject',
      -- checks inside security-invoker read functions (they only refuse, never write)
      'require_run','require_tool','raise_denied',
      -- called by triggers that run as the signed-in user (territory rules are public inside the company)
      'match_territory')
  loop
    execute format('grant execute on function %s to authenticated', f.sig);
  end loop;
end $$;

grant execute on all functions in schema ea_private to service_role;
grant execute on all functions in schema public to service_role;

-- Functions added to ea_private later start with no execute for signed-in users, so the
-- allowlist above has to be extended on purpose.
alter default privileges in schema ea_private revoke execute on functions from public;
