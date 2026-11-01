"""Sidecar mode, against fake Salesforce and HubSpot HTTP sessions (no real org or portal)."""
import json
import pathlib
import sys

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sidecars.salesforce import sf_sidecar  # noqa: E402
from sidecars.hubspot import hs_sidecar  # noqa: E402
from sidecars.common.mirror import writeback  # noqa: E402
from helpers import ADMIN_DSN, ANA, CY, agent_uid, build  # noqa: E402


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.text = status, body, json.dumps(body) if body is not None else ""

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSF:
    def __init__(self):
        self.headers, self.patches = {}, []

    def get(self, url, params=None, timeout=None):
        q = params["q"]
        if "FROM Account" in q:
            recs = [{"Id": "001A", "Name": "Granite Works", "OwnerId": "005ANA", "EA_Territory_Key__c": "WEST-ENT"}]
        elif "FROM Opportunity" in q:
            recs = [{"Id": "006A", "Name": "Granite Works - Platform", "OwnerId": "005ANA", "Account": {"EA_Territory_Key__c": "WEST-ENT"}}]
        else:
            recs = [{"Id": "003A", "Name": "Jordan Lee", "OwnerId": "005ANA", "Account": {"EA_Territory_Key__c": "WEST-ENT"}}]
        return Resp(200, {"records": recs})

    def patch(self, url, json=None, timeout=None):
        self.patches.append((url, json))
        return Resp(204)


class FakeHS:
    def __init__(self):
        self.headers, self.patches = {}, []

    def post(self, url, json=None, timeout=None):
        obj = url.split("/objects/")[1].split("/")[0]
        props = {"companies": {"name": "Granite Works", "hubspot_owner_id": "77", "ea_territory_key": "WEST-ENT"},
                 "deals": {"dealname": "Granite Works - Platform", "hubspot_owner_id": "77"},
                 "contacts": {"lastname": "Lee", "hubspot_owner_id": "77"}}[obj]
        return Resp(200, {"results": [{"id": f"{obj}-1", "properties": props}]})

    def patch(self, url, json=None, timeout=None):
        self.patches.append((url, json))
        return Resp(200, {})


@pytest.fixture(scope="module")
def sdsn():
    dsn = build(ADMIN_DSN, "ea_test_sidecar", seed=True)
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("insert into public.sidecar_user_map values ('salesforce','005ANA',(select id from public.sales where user_id = %s)),"
                  "('hubspot','77',(select id from public.sales where user_id = %s))", (ANA, ANA))
        c.execute("insert into public.sidecar_territory_map values ('salesforce','WEST-ENT',2), ('hubspot','WEST-ENT',2)")
    return dsn


def act(c, uid):
    c.execute("set local role authenticated")
    c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def test_salesforce_ingest_review_and_writeback(sdsn):
    fake = FakeSF()
    sf = sf_sidecar.Salesforce("https://example.my.salesforce.com", "token", session=fake)
    with psycopg.connect(sdsn) as c:
        assert sf_sidecar.ingest(c, sf, "2026-01-01T00:00:00Z") == 3
        c.commit()
        row = c.execute("select owner_sales_id is not null, territory_id from public.external_subjects where subject_id = '006A'").fetchone()
        assert row == (True, 2)
        cap = c.execute("select id from public.agent_definitions where name = 'conversation-capture'").fetchone()[0]
        c.execute("select set_config('ea.promotion_in_progress','on',false)")
        c.execute("update public.agent_definitions set autonomy_level = 2 where id = %s", (cap,))
        c.execute("select set_config('ea.promotion_in_progress','',false)")
        c.commit()
        with c.transaction():
            act(c, agent_uid(cap))
            run = c.execute("select public.start_run('scripted','v1')").fetchone()[0]
            ev = c.execute("select public.record_evidence(%s,'deal','006A','call_quote','\"Legal has the order form.\"','gong://1#3:10',now())", (run,)).fetchone()[0]
            payload = json.dumps({"system": "salesforce", "object": "Opportunity", "field": "StageName", "value": "Negotiation"})
            dec = c.execute("select public.propose_decision(%s,'update_external_field','deal','006A','Order form with legal', array[%s]::bigint[], %s::jsonb)",
                            (run, ev, payload)).fetchone()[0]
            assert c.execute("select public.propose_external_update(%s,%s,'salesforce','Opportunity','006A','StageName','\"Negotiation\"')",
                             (run, dec)).fetchone()[0] == "pending_approval"
            bad = c.execute("select public.propose_decision(%s,'update_external_field','deal','006A','Change amount', array[%s]::bigint[], %s::jsonb)",
                            (run, ev, json.dumps({"system": "salesforce", "object": "Opportunity", "field": "Amount", "value": 1}))).fetchone()[0]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction():
                    c.execute("select public.propose_external_update(%s,%s,'salesforce','Opportunity','006A','Amount','1')", (run, bad))
        with c.transaction():
            act(c, CY)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction():
                    c.execute("select public.review_decision(%s,'accepted')", (dec,))
        with c.transaction():
            act(c, ANA)
            assert c.execute("select public.review_decision(%s,'accepted')", (dec,)).fetchone()[0] == "approved"
        assert writeback(c, "salesforce", sf_sidecar.send_change(sf)) == {"sent": 1, "failed": 0}
        url, body = fake.patches[0]
        assert url.endswith("/sobjects/Opportunity/006A") and body == {"StageName": "Negotiation", "EA_Decision_Id__c": str(dec)}
        assert c.execute("select status from public.decisions where id = %s", (dec,)).fetchone()[0] == "applied"


def test_hubspot_ingest_and_patch_shape(sdsn):
    fake = FakeHS()
    hs = hs_sidecar.HubSpot("token", session=fake)
    with psycopg.connect(sdsn) as c:
        assert hs_sidecar.ingest(c, hs, 0) == 3
        assert c.execute("select territory_id from public.external_subjects where subject_id = 'companies-1'").fetchone()[0] == 2
    hs_sidecar.send_change(hs)({"object_name": "deals", "record_id": "deals-1", "field": "dealstage", "value": "contractsent", "decision_id": 9})
    assert fake.patches[0] == ("https://api.hubapi.com/crm/v3/objects/deals/deals-1",
                               {"properties": {"dealstage": "contractsent", "ea_decision_id": "9"}})


def test_only_the_worker_claims_changes(sdsn):
    with psycopg.connect(sdsn) as c, c.transaction():
        act(c, ANA)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from public.claim_outbound_changes('salesforce')")
