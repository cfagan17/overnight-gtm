import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FileText, Gavel, Handshake, Lightbulb, Send } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { day, money, time } from '../lib/format';
import { STAGES } from '../lib/meta';
import { ActionBadge, Badge, Card, Empty, Err, LoopBadge, Outcome, Page, Spinner, Strength, Tabs } from '../components/ui';
import { PlanView } from '../components/Plan';

export default function Account() {
  const { id } = useParams();
  const cid = Number(id);
  const [tab, setTab] = useState('why');
  const { data, error, loading } = useLoad(async () => {
    const co = await q(supabase.from('companies').select('*').eq('id', cid).maybeSingle());
    if (!co) throw new Error('Not found, or not visible to you.');
    const contacts = (await q(supabase.from('contacts').select('id, first_name, last_name, title, status').eq('company_id', cid))) as any[];
    const cids = contacts.map((c) => String(c.id));
    const deals = (await q(supabase.from('deals').select('*').eq('company_id', cid))) as any[];
    const dids = deals.map((d) => String(d.id));
    const [owner, terr, contracts, evC, evP, evD, decC, decP, decD, strats, touches, commits] = await Promise.all([
      q(supabase.from('sales').select('first_name, last_name').eq('id', co.sales_id).maybeSingle()),
      q(supabase.from('territories').select('name').eq('id', co.territory_id).maybeSingle()),
      q(supabase.from('contracts').select('*').eq('company_id', cid)),
      q(supabase.from('evidence').select('*').eq('subject_type', 'company').eq('subject_id', String(cid))),
      cids.length ? q(supabase.from('evidence').select('*').eq('subject_type', 'contact').in('subject_id', cids)) : Promise.resolve([]),
      dids.length ? q(supabase.from('evidence').select('*').eq('subject_type', 'deal').in('subject_id', dids)) : Promise.resolve([]),
      q(supabase.from('decisions').select('*').eq('subject_type', 'company').eq('subject_id', String(cid))),
      cids.length ? q(supabase.from('decisions').select('*').eq('subject_type', 'contact').in('subject_id', cids)) : Promise.resolve([]),
      dids.length ? q(supabase.from('decisions').select('*').eq('subject_type', 'deal').in('subject_id', dids)) : Promise.resolve([]),
      q(supabase.from('strategies').select('*').eq('subject_type', 'company').eq('subject_id', String(cid)).order('version', { ascending: false })),
      cids.length ? q(supabase.from('touches').select('*').in('contact_id', contacts.map((c) => c.id))) : Promise.resolve([]),
      q(supabase.from('commitments').select('*').eq('subject_type', 'company').eq('subject_id', String(cid))),
    ]);
    return { co, contacts, deals, owner, terr, contracts: contracts as any[], evidence: [...(evC as any[]), ...(evP as any[]), ...(evD as any[])],
      decisions: [...(decC as any[]), ...(decP as any[]), ...(decD as any[])], strats: strats as any[], touches: touches as any[], commits: commits as any[] };
  }, [cid]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Account"><Err e={error || ''} /></Page>;
  const { co, contacts, deals, owner, terr, contracts, evidence, decisions, strats, touches, commits } = data;
  const cname = Object.fromEntries(contacts.map((c) => [c.id, `${c.first_name} ${c.last_name}`]));
  const cfull = Object.fromEntries(contacts.map((c) => [c.id, `${c.first_name} ${c.last_name}, ${c.title}`]));
  const events = [
    ...evidence.map((e) => ({ at: e.observed_at, kind: 'evidence', e })),
    ...decisions.map((d) => ({ at: d.made_at, kind: 'decision', d })),
    ...decisions.filter((d) => d.reviewed_at).map((d) => ({ at: d.reviewed_at, kind: 'review', d })),
    ...strats.map((s) => ({ at: s.created_at, kind: 'plan', s })),
    ...touches.map((t) => ({ at: t.scheduled_for || t.created_at, kind: 'touch', t })),
    ...commits.map((m) => ({ at: m.created_at, kind: 'commitment', m })),
  ].sort((a, b) => +new Date(b.at) - +new Date(a.at));
  const icon: any = { evidence: Lightbulb, decision: Gavel, review: Gavel, plan: FileText, touch: Send, commitment: Handshake };
  const color: any = { evidence: '#a78bfa', decision: '#fbbf24', review: '#f472b6', plan: '#60a5fa', touch: '#34d399', commitment: '#f472b6' };
  const latest = strats[0];

  return (
    <Page kicker={<Link to="/accounts" className="hover:text-ink">Accounts</Link>} title={co.name}
      actions={<div className="flex flex-wrap gap-2"><Badge color="#60a5fa">{terr?.name}</Badge><Badge color="#93a0bb">owner {owner ? `${owner.first_name} ${owner.last_name}` : '—'}</Badge><Badge color="#93a0bb">{co.segment}, {co.state_abbr}</Badge></div>}>
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div>
          <Tabs value={tab} onChange={setTab} tabs={[{ id: 'why', label: `Why timeline (${events.length})` }, { id: 'plan', label: `Plans (${strats.length})` }, { id: 'evidence', label: `Evidence (${evidence.length})` }]} />
          {tab === 'why' && (
            <div className="card p-5">
              <div className="mb-4 text-sm text-ink-muted">Everything the system knows about why this account is where it is: what was observed, what the agents decided, how people reviewed it, and what happened.</div>
              <ol className="relative space-y-4 border-l border-night-600 pl-6">
                {events.map((ev: any, i) => {
                  const I = icon[ev.kind];
                  return (
                    <li key={i} className="relative">
                      <span className="absolute -left-[35px] grid h-6 w-6 place-items-center rounded-full ring-4 ring-night-800" style={{ background: color[ev.kind] }}><I size={13} color="#0b1020" /></span>
                      <div className="text-xs text-ink-faint">{time(ev.at)}</div>
                      {ev.kind === 'evidence' && <div className="mt-1 text-sm">{ev.e.claim} <span className="ml-1 inline-flex gap-1 align-middle"><Strength s={ev.e.strength} /><Badge color="#5d6985">{ev.e.kind.replace(/_/g, ' ')}</Badge></span></div>}
                      {ev.kind === 'decision' && <div className="mt-1 text-sm"><span className="mr-2 inline-flex gap-1 align-middle"><LoopBadge loop={ev.d.loop} /><ActionBadge action={ev.d.action} /></span>{ev.d.rationale}</div>}
                      {ev.kind === 'review' && <div className="mt-1 text-sm">Reviewed: <Outcome o={ev.d.review_outcome} /> {ev.d.review_note && <span className="text-ink-muted">“{ev.d.review_note}”</span>}</div>}
                      {ev.kind === 'plan' && <div className="mt-1 text-sm">Plan version {ev.s.version} <Badge color="#60a5fa">{ev.s.status}</Badge></div>}
                      {ev.kind === 'touch' && <div className="mt-1 text-sm">{ev.t.channel} to {cname[ev.t.contact_id]}, sent by {ev.t.sender_type}: {ev.t.purpose} <Badge color="#34d399">{ev.t.status.replace('_', ' ')}</Badge></div>}
                      {ev.kind === 'commitment' && <div className="mt-1 text-sm">We promised: {ev.m.promise} <Badge color="#f472b6">{ev.m.status}</Badge></div>}
                    </li>
                  );
                })}
              </ol>
              {!events.length && <Empty>Nothing recorded yet.</Empty>}
            </div>
          )}
          {tab === 'plan' && (
            <div className="space-y-4">
              {strats.map((s) => {
                const d = decisions.find((x) => x.id === s.decision_id);
                return (
                  <Card key={s.id} title={<>Version {s.version} <span className="ml-2 font-normal text-ink-muted">{day(s.created_at)}</span></>} right={<div className="flex gap-2"><Badge color="#60a5fa">{s.status}</Badge>{d && <Outcome o={d.review_outcome} />}</div>}>
                    {d?.review_note && <div className="mb-4 rounded-xl bg-people/10 px-4 py-3 text-sm"><span className="font-semibold text-people">Reviewer: </span>“{d.review_note}”</div>}
                    <PlanView plan={s.plan} contacts={cfull} />
                  </Card>
                );
              })}
              {!strats.length && <Empty>No plans yet.</Empty>}
            </div>
          )}
          {tab === 'evidence' && (
            <div className="card divide-y divide-night-600/60">
              {evidence.sort((a, b) => +new Date(b.observed_at) - +new Date(a.observed_at)).map((e) => (
                <div key={e.id} className="px-5 py-3"><div className="text-sm">{e.claim}</div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-ink-faint"><Strength s={e.strength} /><span>{e.kind.replace(/_/g, ' ')}</span><span className="font-mono">{e.source_uri}</span><span>{time(e.observed_at)}</span>{e.downgraded && <Badge color="#f87171">downgraded</Badge>}</div></div>
              ))}
            </div>
          )}
        </div>
        <div className="space-y-4">
          {latest && <Card title="Current plan"><div className="flex items-center gap-2 text-sm">Version {latest.version} <Badge color="#60a5fa">{latest.status}</Badge></div>{latest.plan?.sender && <div className="mt-2 text-sm text-ink-muted">Sender: <b className="text-ink">{latest.plan.sender.type}</b></div>}</Card>}
          <Card title="Deals" pad={false}>
            <ul className="divide-y divide-night-600/60">{deals.map((d) => (
              <li key={d.id} className="px-5 py-3"><div className="text-sm font-semibold">{d.name}</div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs"><span className="tabular-nums font-semibold">{money(d.amount)}</span><Badge color="#fbbf24">{STAGES.find((s) => s.id === d.stage)?.name}</Badge><Badge color="#93a0bb">{d.forecast_category}</Badge><span className="text-ink-faint">close {d.expected_closing_date}</span></div></li>
            ))}</ul>
          </Card>
          <Card title="Buying group" pad={false}>
            <ul className="divide-y divide-night-600/60">{contacts.map((c) => (
              <li key={c.id} className="px-5 py-3"><div className="text-sm font-semibold">{c.first_name} {c.last_name}</div><div className="text-xs text-ink-muted">{c.title}</div></li>
            ))}</ul>
          </Card>
          {contracts.length > 0 && <Card title="Contracts" pad={false}><ul className="divide-y divide-night-600/60">{contracts.map((k) => (
            <li key={k.id} className="px-5 py-3 text-sm"><span className="font-semibold tabular-nums">{money(k.arr_usd)}</span> ARR <span className="text-ink-muted">ends {k.ends_on}{k.auto_renew ? ', auto-renews' : ''}</span></li>))}</ul></Card>}
        </div>
      </div>
    </Page>
  );
}
