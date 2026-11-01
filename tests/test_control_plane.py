"""Layer 2: legitimate work still succeeds, and the boundaries hold."""
from helpers import ANA, BEN, CY, EAST_MGR, FIN, OWNER, PAT, VP, WEST_MGR, acting_as, attempt, scalar


def visible_deals(conn, uid):
    with acting_as(conn, uid):
        return scalar(conn, "select count(*) from public.deals")


def test_visibility_by_role(conn):
    total = scalar(conn, "select count(*) from public.deals")
    assert visible_deals(conn, OWNER) == total
    assert visible_deals(conn, FIN) == total                     # read-only sees everything
    assert visible_deals(conn, VP) == total                      # manages both regions
    west = scalar(conn, "select count(*) from public.deals d join public.territories t on t.id = d.territory_id where t.region = 'West'")
    assert visible_deals(conn, WEST_MGR) == west                 # own team only
    assert visible_deals(conn, EAST_MGR) == total - west
    ana_own = scalar(conn, "select count(*) from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s", (ANA,))
    assert visible_deals(conn, ANA) == ana_own
    assert 0 < visible_deals(conn, BEN) < west


def test_rep_works_own_records(conn):
    deal = scalar(conn, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s limit 1", (ANA,))
    with acting_as(conn, ANA):
        assert attempt(conn, "update public.deals set amount = amount + 1 where id = %s", (deal,))[2] == 1
        company = scalar(conn, "select company_id from public.deals where id = %s", (deal,))
        # new records default to the rep as owner (Atomic's trigger) and pass the policy
        st, rows, _ = attempt(conn, "insert into public.deals (name, company_id, stage, amount) values ('New', %s, 'opportunity', 10) returning sales_id", (company,))
        assert st == "ok"
        contact = scalar(conn, "select id from public.contacts where company_id = %s limit 1", (company,))
        assert attempt(conn, "insert into public.contact_notes (contact_id, text, sales_id) values (%s, 'hi', (select id from public.sales where user_id = auth.uid()))", (contact,))[0] == "ok"
        # reps archive, they do not delete
        assert attempt(conn, "delete from public.deals where id = %s", (deal,))[2] == 0
        assert attempt(conn, "update public.deals set archived_at = now() where id = %s", (deal,))[2] == 1


def test_manager_edits_team_but_not_other_team(conn):
    ana_deal = scalar(conn, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s limit 1", (ANA,))
    cy_deal = scalar(conn, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s limit 1", (CY,))
    with acting_as(conn, WEST_MGR):
        assert attempt(conn, "update public.deals set amount = 5 where id = %s", (ana_deal,))[2] == 1
        assert attempt(conn, "update public.deals set amount = 5 where id = %s", (cy_deal,))[2] == 0
        assert attempt(conn, "delete from public.deals where id = %s", (ana_deal,))[2] == 1   # managers may delete their team's records


def test_discount_and_margin_are_masked(conn):
    deal = scalar(conn, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s limit 1", (ANA,))
    with acting_as(conn, ANA):
        assert attempt(conn, "select discount_pct from public.deal_lines")[0] == "denied"
        assert attempt(conn, "select arr_usd from public.deal_lines where deal_id = %s", (deal,))[0] == "ok"
        assert conn.execute("select * from public.deal_line_discounts(%s)", (deal,)).fetchall() == []
        assert attempt(conn, "select margin_pct from public.partners")[0] == "denied"
        assert scalar(conn, "select public.partner_margin(1)") is None
    with acting_as(conn, WEST_MGR):
        assert len(conn.execute("select * from public.deal_line_discounts(%s)", (deal,)).fetchall()) >= 1
    with acting_as(conn, PAT):
        assert scalar(conn, "select public.partner_margin(1)") == 15


def test_territory_carve_is_owner_only(conn):
    with acting_as(conn, WEST_MGR):
        assert attempt(conn, "update public.territory_rules set priority = priority + 100")[2] == 0
        assert attempt(conn, "insert into public.territory_members values (4, (select id from public.sales where user_id = auth.uid()), 'member')")[0] == "denied"
    with acting_as(conn, OWNER):
        assert attempt(conn, "update public.territory_rules set priority = priority + 100 where territory_id = 2")[2] == 1


def test_audit_log_records_and_is_locked(conn):
    deal = scalar(conn, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s limit 1", (ANA,))
    with acting_as(conn, ANA):
        assert attempt(conn, "select count(*) from public.audit_log")[1][0][0] == 0      # reps cannot read the log
        assert attempt(conn, "delete from public.audit_log")[0] == "denied"
        assert attempt(conn, "insert into public.audit_log (table_name, op) values ('x','x')")[0] == "denied"
        # a human cannot forge agent attribution by setting the session variable
        conn.execute("select set_config('ea.decision_id', '1', true)")
        conn.execute("update public.deals set amount = 779 where id = %s", (deal,))
        conn.execute("reset role")
        row = conn.execute("select principal_id::text, principal_kind, decision_id, after->>'amount' from public.audit_log "
                           "where table_name = 'deals' and row_id = %s order by id desc limit 1", (str(deal),)).fetchone()
    assert row == (ANA, "human", None, "779")


def test_forecast_snapshot(conn):
    with acting_as(conn, ANA):
        assert attempt(conn, "select public.take_forecast_snapshot()")[0] == "denied"
    with acting_as(conn, OWNER):
        n = scalar(conn, "select public.take_forecast_snapshot()")
        assert n > 0
        assert scalar(conn, "select public.take_forecast_snapshot()") == 0           # idempotent per week


def test_agents_are_not_sellers(conn):
    # Atomic gives every auth user a sales row; agent accounts have theirs removed.
    assert scalar(conn, "select count(*) from public.sales where email like '%%@agents.%%'") == 0
