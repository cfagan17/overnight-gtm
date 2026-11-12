import { useState } from 'react';
import { supabase, errText } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, pct, time } from '../lib/format';
import { loopName } from '../lib/meta';
import { Badge, Card, Err, Page, Spinner, toast } from '../components/ui';

export function Policies() {
  const { me } = useSession();
  const [contact, setContact] = useState('');
  const [reason, setReason] = useState('');
  const { data, error, loading, reload } = useLoad(async () => {
    const [pol, dnc, grants, defs, rules, sources, contacts] = await Promise.all([
      q(supabase.from('policies').select('*').order('id')),
      q(supabase.from('do_not_contact').select('*').order('added_at', { ascending: false })),
      q(supabase.from('agent_grants').select('*')),
      q(supabase.from('agent_definitions').select('id, name, loop, autonomy_level, max_autonomy')),
      q(supabase.from('promotion_rules').select('*').order('to_level')),
      q(supabase.from('evidence_sources').select('*')),
      q(supabase.from('contacts').select('id, first_name, last_name, company_id').order('last_name')),
    ]);
    return { pol: pol as any[], dnc: dnc as any[], grants: grants as any[], defs: defs as any[], rules: rules as any[], sources: sources as any[], contacts: contacts as any[] };
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Policies and grants"><Err e={error || ''} /></Page>;
  const cname = Object.fromEntries(data.contacts.map((c) => [c.id, `${c.first_name} ${c.last_name}`]));
  async function addDnc() {
    const { error } = await supabase.from('do_not_contact').insert({ contact_id: Number(contact), reason, added_by: me?.userId });
    if (error) return toast(errText(error), 'err');
    toast('Added. Every loop is blocked from contacting them, in the database.'); setContact(''); setReason(''); reload();
  }
  return (
    <Page kicker="Layer 2, the control plane" title="Policies and grants">
      <p className="-mt-3 mb-6 max-w-3xl text-ink-muted">These rules live in the database, not in prompts. Every touch and every change an agent proposes is checked against them before anything happens, whatever the agent was told.</p>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Rules of engagement" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.pol.map((p) => (
            <li key={p.id} className="flex items-start gap-3 px-5 py-3"><div className="flex-1"><div className="text-sm font-semibold">{p.name}</div><div className="mt-0.5 font-mono text-xs text-ink-faint">{p.rule_type} {JSON.stringify(p.params)}</div></div><Badge color={p.active ? '#047857' : '#71717a'}>{p.active ? 'on' : 'off'}</Badge></li>
          ))}</ul>
        </Card>
        <Card title="Do not contact" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.dnc.map((d) => (
            <li key={d.contact_id} className="px-5 py-3 text-sm"><span className="font-semibold">{cname[d.contact_id] || `Contact ${d.contact_id}`}</span> <span className="text-ink-muted">{d.reason}</span><div className="text-xs text-ink-faint">{ago(d.added_at)}</div></li>
          ))}{!data.dnc.length && <li className="px-5 py-4 text-sm text-ink-muted">Nobody yet.</li>}</ul>
          <div className="space-y-2 border-t border-night-600/60 p-4">
            <select className="input" value={contact} onChange={(e) => setContact(e.target.value)}><option value="">Add a contact…</option>{data.contacts.map((c) => <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>)}</select>
            <div className="flex gap-2"><input className="input" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} /><button className="btn-primary" disabled={!contact || !reason} onClick={addDnc}>Add</button></div>
          </div>
        </Card>
        <Card title="What each agent may do" pad={false} className="xl:col-span-2">
          <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-sm">
            <thead><tr className="border-b border-night-600/60 text-left">{['Agent', 'Level / cap', 'Tools granted', 'Scope'].map((h) => <th key={h} className="label px-5 py-3">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-night-600/50">{data.defs.map((d) => {
              const g = data.grants.filter((x) => x.agent_definition_id === d.id);
              return (
                <tr key={d.id}><td className="px-5 py-3 font-semibold">{loopName(d.loop)}</td><td className="px-5 py-3">{d.autonomy_level} / {d.max_autonomy}</td>
                  <td className="px-5 py-3"><div className="flex flex-wrap gap-1">{g.map((x) => <span key={x.tool} className="rounded-md bg-night-700 px-1.5 py-0.5 font-mono text-[11px]">{x.tool}</span>)}</div></td>
                  <td className="px-5 py-3 font-mono text-xs text-ink-muted">{g[0] ? JSON.stringify(g[0].scope) : '—'}</td></tr>
              );
            })}</tbody>
          </table></div>
        </Card>
        <Card title="The bar to move up a level" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.rules.map((r) => (
            <li key={r.to_level} className="px-5 py-3 text-sm"><span className="font-bold">To level {r.to_level}: </span><span className="text-ink-muted">{r.min_reviewed} reviewed, {pct(r.min_accepted_as_is)} accepted as is, at most {pct(r.max_rejected)} rejected{r.needs_zero_violations ? ', zero violations' : ''}{r.needs_replay_at_least_baseline ? ', replay at least baseline' : ''}{r.needs_audit_better_than_human ? ', audited error rate below the human one' : ''}.</span></li>
          ))}</ul>
        </Card>
        <Card title="Registered evidence sources" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.sources.map((s) => (
            <li key={s.uri_prefix} className="flex items-center gap-3 px-5 py-3 text-sm"><span className="font-mono">{s.uri_prefix}</span><span className="flex-1 text-ink-muted">{s.description}</span>{s.agents_may_write ? <Badge color="#b45309">agents may write</Badge> : <Badge color="#047857">integration only</Badge>}</li>
          ))}</ul>
        </Card>
      </div>
    </Page>
  );
}

export function Audit() {
  const { me } = useSession();
  const [setup, setSetup] = useState(false);
  const { data, error, loading } = useLoad(async () => {
    let qq = supabase.from('audit_log').select('id, table_name, row_id, op, principal_kind, principal_id, decision_id, run_id, at').order('at', { ascending: false }).limit(150);
    if (!setup) qq = qq.in('principal_kind', ['human', 'agent']);
    return q(qq) as Promise<any[]>;
  }, [me?.userId, setup]);
  if (loading) return <Spinner />;
  return (
    <Page kicker="Layer 2, the control plane" title="Audit log">
      <p className="-mt-3 mb-4 max-w-3xl text-ink-muted">Every change to the ledger and to governance tables, with who made it: a person, or an agent with the decision and run behind it. Reps cannot read it. Nobody can edit it.</p>
      <label className="mb-4 flex items-center gap-2 text-sm text-ink-muted"><input type="checkbox" checked={setup} onChange={(e) => setSetup(e.target.checked)} />Show setup changes (installs and the demo loader)</label>
      {error ? <Err e={error} /> : !data?.length ? <div className="card p-6 text-sm text-ink-muted">{me?.role === 'owner' || me?.role === 'readonly' ? (setup ? 'Nothing yet.' : 'No changes by people or agents since the demo was loaded. Accept something in the review inbox and it shows up here, or tick the box above to see the setup changes.') : 'Nothing visible to you. Only owners and read-only users see the audit log.'}</div> : (
        <div className="card overflow-x-auto"><table className="w-full min-w-[760px] text-sm">
          <thead><tr className="border-b border-night-600/60 text-left">{['When', 'Table', 'Row', 'Change', 'By', 'Decision', 'Run'].map((h) => <th key={h} className="label px-5 py-3">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-night-600/50">{data.map((a) => (
            <tr key={a.id}><td className="px-5 py-2.5 text-ink-muted">{time(a.at)}</td><td className="px-5 py-2.5 font-mono text-xs">{a.table_name}</td><td className="px-5 py-2.5 font-mono text-xs text-ink-faint">{a.row_id}</td>
              <td className="px-5 py-2.5"><Badge color={a.op === 'DELETE' ? '#b91c1c' : a.op === 'INSERT' ? '#047857' : '#b45309'}>{a.op.toLowerCase()}</Badge></td>
              <td className="px-5 py-2.5"><Badge color={a.principal_kind === 'agent' ? '#1d4ed8' : '#0f766e'}>{!a.principal_kind || a.principal_kind === 'none' ? 'setup' : a.principal_kind}</Badge></td>
              <td className="px-5 py-2.5 font-mono text-xs">{a.decision_id || ''}</td><td className="px-5 py-2.5 font-mono text-xs">{a.run_id || ''}</td></tr>
          ))}</tbody></table></div>
      )}
    </Page>
  );
}
