import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowDown, ArrowUp, Check, X } from 'lucide-react';
import { supabase, errText } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, day, pct, time } from '../lib/format';
import { LEVELS, LEVEL_HELP, LOOP } from '../lib/meta';
import { ActionBadge, Badge, Bar, Card, Err, Ladder, Outcome, Page, Spinner, Tabs, toast } from '../components/ui';

function lineDiff(a: string, b: string) {
  const A = a.split('\n'), Bs = new Set(A), Bl = b.split('\n'), As = new Set(Bl);
  return { removed: A.filter((l) => !As.has(l)), added: Bl.filter((l) => !Bs.has(l)) };
}

export default function Loop() {
  const { loop = '' } = useParams();
  const meta = LOOP[loop];
  const { me } = useSession();
  const owner = me?.role === 'owner';
  const [tab, setTab] = useState('trust');
  const [draft, setDraft] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const { data, error, loading, reload } = useLoad(async () => {
    const def = await q(supabase.from('agent_definitions').select('*').eq('loop', loop).single());
    const [prompts, decs, runs, changes, replay, viol, overrides] = await Promise.all([
      q(supabase.from('loop_prompts').select('*').eq('loop', loop).order('version', { ascending: false })),
      q(supabase.from('decisions').select('id, action, subject_type, subject_id, rationale, review_outcome, review_note, made_at').eq('loop', loop).order('made_at', { ascending: false }).limit(200)),
      q(supabase.from('runs').select('id, model, prompt_version, started_at, ended_at, tokens_in, status').eq('loop', loop).order('started_at', { ascending: false }).limit(25)),
      q(supabase.from('autonomy_changes').select('*').eq('agent_definition_id', def.id).order('decided_at', { ascending: false })),
      q(supabase.from('replay_results').select('*').eq('agent_definition_id', def.id).order('run_at')),
      q(supabase.from('policy_violations').select('*').eq('agent_definition_id', def.id).order('flagged_at', { ascending: false })),
      q(supabase.from('insight_overrides').select('*').eq('loop', loop)),
    ]);
    let check: any = null;
    if (def.autonomy_level < def.max_autonomy) {
      const r = await supabase.rpc('promotion_check', { p_agent_definition_id: def.id, p_to_level: def.autonomy_level + 1 });
      check = r.error ? { error: errText(r.error) } : r.data;
    }
    return { def, prompts: prompts as any[], decs: decs as any[], runs: runs as any[], changes: changes as any[], replay: replay as any[], viol: viol as any[], overrides: overrides as any[], check };
  }, [loop, me?.userId]);
  if (loading && !data) return <Spinner />;
  if (error || !data) return <Page title={meta?.name || loop}><Err e={error || ''} /></Page>;
  const { def, prompts, decs, runs, changes, replay, viol, overrides, check } = data;
  const approved = prompts.find((p) => p.status === 'approved');
  const proposed = prompts.filter((p) => p.status === 'proposed');
  const reviewed = decs.filter((d) => d.review_outcome);
  const n = (o: string) => reviewed.filter((d) => d.review_outcome === o).length;

  async function call(fn: string, args: any, ok: string) {
    setBusy(true);
    const { error } = await supabase.rpc(fn, args);
    setBusy(false);
    if (error) return toast(errText(error), 'err');
    toast(ok); setDraft(null); setNote(''); setReason(''); reload();
  }

  return (
    <Page kicker={<Link to="/loops" className="hover:text-ink">Loops / {meta?.area}</Link>} title={meta?.name || loop}
      actions={<div className="flex items-center gap-3"><Ladder level={def.autonomy_level} max={def.max_autonomy} /><Badge color="#b45309" solid>Level {def.autonomy_level}: {LEVELS[def.autonomy_level]}</Badge></div>}>
      <p className="-mt-3 mb-6 max-w-3xl text-ink-muted">{meta?.job} Runs {meta?.cadence.toLowerCase()}. {LEVEL_HELP[def.autonomy_level]}</p>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'trust', label: 'Trust and promotion' }, { id: 'prompt', label: <>Prompt {proposed.length > 0 && <span className="ml-1 rounded-full bg-prim px-1.5 text-[11px] text-night-950">{proposed.length}</span>}</> },
        { id: 'decisions', label: `Decisions (${decs.length})` }, { id: 'runs', label: 'Runs' }]} />

      {tab === 'trust' && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Review record, last 60 days">
            <Bar parts={[{ v: n('accepted'), c: '#047857' }, { v: n('edited'), c: '#b45309' }, { v: n('rejected'), c: '#b91c1c' }]} />
            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
              {[['accepted', '#047857'], ['edited', '#b45309'], ['rejected', '#b91c1c']].map(([o, c]) => (
                <div key={o} className="rounded-md bg-night-850 p-3"><div className="text-2xl font-semibold tabular-nums" style={{ color: c }}>{reviewed.length ? pct(n(o) / reviewed.length) : '—'}</div><div className="text-xs text-ink-muted">{o} ({n(o)})</div></div>
              ))}
            </div>
            {overrides.length > 0 && <div className="mt-5"><div className="label mb-2">What reviewers keep saying</div>
              <ul className="space-y-1.5 text-sm">{overrides.flatMap((o) => o.recent_notes || []).slice(0, 4).map((t: string, i: number) => <li key={i} className="rounded bg-night-850 px-3 py-2 text-ink-muted">“{t}”</li>)}</ul></div>}
          </Card>
          <Card title={def.autonomy_level < def.max_autonomy ? `Promotion check: level ${def.autonomy_level} to ${def.autonomy_level + 1}` : 'At its cap'}>
            {def.autonomy_level >= def.max_autonomy ? (
              <div className="text-sm text-ink-muted">This loop is at its maximum level ({def.max_autonomy}).{def.max_autonomy <= 2 && ' Pay, territories and process design always need a human signature, enforced by a database constraint.'}</div>
            ) : check?.error ? <div className="text-sm text-ink-muted">{check.error}</div> : check && (
              <>
                <ul className="space-y-2">{check.checks.map((c: any, i: number) => (
                  <li key={i} className="flex items-center gap-3 text-sm">
                    <span className={`grid h-5 w-5 place-items-center rounded-full ${c.pass ? 'bg-control/20 text-control' : 'bg-red-500/15 text-red-700'}`}>{c.pass ? <Check size={13} /> : <X size={13} />}</span>
                    <span className="flex-1">{c.check}</span>
                    <span className="font-mono text-xs text-ink-muted">{typeof c.have === 'object' && c.have ? `${c.have.model} ${Number(c.have.score).toFixed(2)} vs ${Number(c.have.baseline).toFixed(2)}` : `${c.have ?? '—'}`}{c.need != null && ` / ${c.need}`}{c.need_at_most != null && ` / ≤ ${c.need_at_most}`}</span>
                  </li>
                ))}</ul>
                <div className={`mt-4 rounded-md px-4 py-3 text-sm ${check.eligible ? 'bg-control/10 text-emerald-700' : 'bg-night-850 text-ink-muted'}`}>{check.eligible ? 'Clears the bar. An owner can promote it.' : 'Not yet. The database refuses a promotion until every check passes.'}</div>
              </>
            )}
            {owner && (
              <div className="mt-4 space-y-2 border-t border-night-600/60 pt-4">
                <input className="input" placeholder="Reason (recorded with the change)" value={reason} onChange={(e) => setReason(e.target.value)} />
                <div className="flex flex-wrap gap-2">
                  <button className="btn-green" disabled={busy || !reason || def.autonomy_level >= def.max_autonomy} onClick={() => call('decide_promotion', { p_agent_definition_id: def.id, p_to_level: def.autonomy_level + 1, p_reason: reason }, 'Promoted.')}><ArrowUp size={15} />Promote</button>
                  <button className="btn-red" disabled={busy || !reason || def.autonomy_level === 0} onClick={() => call('decide_promotion', { p_agent_definition_id: def.id, p_to_level: def.autonomy_level - 1, p_reason: reason }, 'Demoted.')}><ArrowDown size={15} />Demote</button>
                </div>
              </div>
            )}
          </Card>
          <Card title="Replay tests by model" right={<span className="text-xs text-ink-faint">When a new model ships, rerun these</span>}>
            <ul className="space-y-3">{replay.map((r) => (
              <li key={r.id}><div className="flex items-baseline justify-between text-sm"><span className="font-mono">{r.model}</span><span className="tabular-nums font-bold">{Number(r.score).toFixed(3)}</span></div>
                <div className="mt-1 h-2 rounded-full bg-night-700"><div className="h-2 rounded-full bg-prim" style={{ width: `${Number(r.score) * 100}%` }} /></div>
                <div className="mt-1 text-xs text-ink-faint">{r.cases} cases, baseline {Number(r.baseline_score).toFixed(3)}, {day(r.run_at)}</div></li>
            ))}{!replay.length && <li className="text-sm text-ink-muted">No replay results yet.</li>}</ul>
          </Card>
          <Card title="Autonomy history" pad={false}>
            <ul className="divide-y divide-night-600/60">
              {viol.map((v) => <li key={'v' + v.id} className="px-5 py-3 text-sm"><Badge color="#b91c1c">violation</Badge> <span className="text-ink-muted">{v.note}</span><div className="mt-1 text-xs text-ink-faint">{time(v.flagged_at)}</div></li>)}
              {changes.map((c) => (
                <li key={c.id} className="px-5 py-3 text-sm"><Badge color={c.to_level > c.from_level ? '#047857' : '#b91c1c'}>{c.from_level} → {c.to_level}</Badge> <span className="text-ink-muted">{c.reason}</span><div className="mt-1 text-xs text-ink-faint">{time(c.decided_at)}</div></li>
              ))}
              {!changes.length && !viol.length && <li className="px-5 py-4 text-sm text-ink-muted">No changes yet. It started at level {def.autonomy_level}.</li>}
            </ul>
          </Card>
        </div>
      )}

      {tab === 'prompt' && (
        <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
          <div className="space-y-6">
            {proposed.map((p) => {
              const df = approved ? lineDiff(approved.body, p.body) : { removed: [], added: p.body.split('\n') };
              return (
                <Card key={p.version} className="border-prim/50" title={<>Proposed version {p.version} <span className="ml-2 font-normal text-ink-muted">{ago(p.created_at)}</span></>} right={<Badge color="#1d4ed8">waiting for an owner</Badge>}>
                  {p.note && <div className="mb-4 text-sm"><span className="text-ink-muted">Why: </span>{p.note}</div>}
                  <div className="space-y-1 rounded-md bg-night-950 p-4 font-mono text-[13px]">
                    {df.removed.map((l, i) => <div key={'r' + i} className="text-red-700">- {l}</div>)}
                    {df.added.map((l, i) => <div key={'a' + i} className="text-emerald-700">+ {l}</div>)}
                  </div>
                  {owner && <div className="mt-4 flex gap-2">
                    <button className="btn-green" disabled={busy} onClick={() => call('approve_prompt', { p_loop: loop, p_version: p.version }, `Version ${p.version} is live. The next run uses it.`)}><Check size={15} />Approve</button>
                    <button className="btn-red" disabled={busy} onClick={() => call('reject_prompt', { p_loop: loop, p_version: p.version }, 'Rejected.')}><X size={15} />Reject</button></div>}
                </Card>
              );
            })}
            <Card title={draft !== null ? 'Edit the prompt' : `Live prompt, version ${approved?.version ?? '—'}`}
              right={owner && draft === null ? <button className="btn-ghost py-1.5" onClick={() => setDraft(approved?.body || '')}>Edit</button> : null}>
              {draft === null ? (
                <div className="whitespace-pre-wrap rounded-md border border-night-600 bg-night-850 p-6 text-[15px] leading-relaxed text-ink">{approved?.body || 'No prompt in the database yet. Runs use the starting version in the repo.'}</div>
              ) : (
                <div className="space-y-3">
                  <textarea className="input h-96 font-mono text-[13px] leading-relaxed" value={draft} onChange={(e) => setDraft(e.target.value)} />
                  <input className="input" placeholder="Why this change? Reviewers and future you will read it." value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="flex gap-2"><button className="btn-primary" disabled={busy || draft === approved?.body} onClick={() => call('propose_prompt_version', { p_loop: loop, p_body: draft, p_note: note || null }, 'Proposed. Approve it to make it live.')}>Propose new version</button>
                    <button className="btn-ghost" onClick={() => setDraft(null)}>Cancel</button></div>
                </div>
              )}
            </Card>
          </div>
          <div className="space-y-6">
            <Card title="How prompts change">
              <ul className="space-y-2 text-sm text-ink-muted">
                <li>Plain English. No code, no tool names.</li>
                <li>Only owners propose and approve. Every change is a new version, in the audit log.</li>
                <li>Every run records the version it used, so results can be compared by version.</li>
              </ul>
            </Card>
            <Card title="Skills this loop follows"><div className="flex flex-wrap gap-2">{meta?.skills.map((s) => <Badge key={s} color="#1d4ed8">{s}</Badge>)}</div></Card>
            <Card title="Versions" pad={false}><ul className="divide-y divide-night-600/60">{prompts.map((p) => (
              <li key={p.version} className="flex items-center gap-2 px-5 py-2.5 text-sm"><span className="font-mono">v{p.version}</span><Badge color={p.status === 'approved' ? '#047857' : p.status === 'proposed' ? '#1d4ed8' : '#71717a'}>{p.status}</Badge><span className="ml-auto text-xs text-ink-faint">{day(p.created_at)}</span></li>
            ))}</ul></Card>
          </div>
        </div>
      )}

      {tab === 'decisions' && (
        <div className="card divide-y divide-night-600/60">{decs.slice(0, 80).map((d) => (
          <div key={d.id} className="flex flex-wrap items-start gap-3 px-5 py-3">
            <div className="w-24 shrink-0 text-xs text-ink-faint">{ago(d.made_at)}</div>
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><ActionBadge action={d.action} />{d.subject_type === 'company' ? <Link className="text-sm font-semibold hover:text-prim" to={`/accounts/${d.subject_id}`}>Account {d.subject_id}</Link> : <span className="text-sm text-ink-muted">{d.subject_type} {d.subject_id}</span>}</div>
              <div className="mt-1 text-sm text-ink-muted">{d.rationale}</div>{d.review_note && <div className="mt-1 text-sm text-people">“{d.review_note}”</div>}</div>
            <Outcome o={d.review_outcome} />
          </div>
        ))}</div>
      )}

      {tab === 'runs' && (
        <div className="card divide-y divide-night-600/60">{runs.map((r) => (
          <Link key={r.id} to={`/runs/${r.id}`} className="flex flex-wrap items-center gap-4 px-5 py-3 text-sm hover:bg-night-750">
            <span className="font-mono text-ink-faint">#{r.id}</span><span>{time(r.started_at)}</span><span className="font-mono text-ink-muted">{r.model}</span><Badge color="#1d4ed8">prompt {r.prompt_version}</Badge>
            <span className="ml-auto text-xs text-ink-faint">{r.ended_at ? `${Math.round((+new Date(r.ended_at) - +new Date(r.started_at)) / 1000)}s` : ''}</span>
          </Link>
        ))}</div>
      )}
    </Page>
  );
}
