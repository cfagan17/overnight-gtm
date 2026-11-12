import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, time } from '../lib/format';
import { LOOPS } from '../lib/meta';
import { ActionBadge, Badge, Card, Err, LoopBadge, Outcome, Page, Spinner, Strength } from '../components/ui';

export function Runs() {
  const { me } = useSession();
  const [loop, setLoop] = useState('');
  const { data, error, loading } = useLoad(async () => {
    let s = supabase.from('runs').select('*').order('started_at', { ascending: false }).limit(150);
    if (loop) s = s.eq('loop', loop);
    return q(s) as Promise<any[]>;
  }, [loop, me?.userId]);
  return (
    <Page kicker="Every agent session is recorded" title="Runs" actions={
      <select className="input w-60" value={loop} onChange={(e) => setLoop(e.target.value)}><option value="">All loops</option>{LOOPS.map((l) => <option key={l.loop} value={l.loop}>{l.name}</option>)}</select>}>
      {loading ? <Spinner /> : error ? <Err e={error} /> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead><tr className="border-b border-night-600/60 text-left">{['Run', 'Loop', 'Started', 'Model', 'Prompt', 'Level', 'Tokens', 'Time'].map((h) => <th key={h} className="label px-5 py-3">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-night-600/50">{(data || []).map((r) => (
              <tr key={r.id} className="hover:bg-night-750">
                <td className="px-5 py-2.5"><Link to={`/runs/${r.id}`} className="font-mono text-prim">#{r.id}</Link></td>
                <td className="px-5 py-2.5"><LoopBadge loop={r.loop} /></td>
                <td className="px-5 py-2.5 text-ink-muted">{ago(r.started_at)}</td>
                <td className="px-5 py-2.5 font-mono text-xs">{r.model}</td>
                <td className="px-5 py-2.5 font-mono text-xs">{r.prompt_version}</td>
                <td className="px-5 py-2.5">{r.autonomy_level}</td>
                <td className="px-5 py-2.5 tabular-nums text-ink-muted">{r.tokens_in ? `${(r.tokens_in / 1000).toFixed(0)}k / ${(r.tokens_out / 1000).toFixed(1)}k` : '—'}</td>
                <td className="px-5 py-2.5 tabular-nums text-ink-muted">{r.ended_at ? `${Math.round((+new Date(r.ended_at) - +new Date(r.started_at)) / 1000)}s` : '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Page>
  );
}

export function Run() {
  const { id } = useParams();
  const { data, error, loading } = useLoad(async () => {
    const r = await q(supabase.from('runs').select('*').eq('id', Number(id)).single());
    const [ev, decs, evid] = await Promise.all([
      q(supabase.from('run_events').select('*').eq('run_id', r.id).order('seq')),
      q(supabase.from('decisions').select('*').eq('run_id', r.id)),
      q(supabase.from('evidence').select('*').eq('run_id', r.id)),
    ]);
    return { r, ev: ev as any[], decs: decs as any[], evid: evid as any[] };
  }, [id]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Run"><Err e={error || ''} /></Page>;
  const { r, ev, decs, evid } = data;
  return (
    <Page kicker={<Link to="/runs" className="hover:text-ink">Runs</Link>} title={<>Run #{r.id}</>}
      actions={<div className="flex flex-wrap gap-2"><LoopBadge loop={r.loop} /><Badge color="#52525b">{r.model}</Badge><Badge color="#1d4ed8">prompt {r.prompt_version}</Badge><Badge color="#b45309">level {r.autonomy_level}</Badge></div>}>
      <div className="mb-6 text-sm text-ink-muted">Started {time(r.started_at)}. {r.tokens_in ? `${r.tokens_in.toLocaleString()} tokens in, ${r.tokens_out.toLocaleString()} out.` : ''} {r.transcript_uri && <>Transcript: <span className="font-mono">{r.transcript_uri}</span></>}</div>
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card title={`Steps (${ev.length})`} pad={false}>
          <ol className="divide-y divide-night-600/60">{ev.map((e) => (
            <li key={e.seq} className="flex items-center gap-3 px-5 py-2.5 text-sm">
              <span className="w-6 font-mono text-xs text-ink-faint">{e.seq}</span>
              <Badge color={e.event_type === 'model_turn' ? '#1d4ed8' : e.event_type === 'tool_call' ? '#b45309' : '#047857'}>{e.event_type.replace('_', ' ')}</Badge>
              <span className="font-mono text-xs">{e.name || ''}</span>
            </li>
          ))}</ol>
        </Card>
        <div className="space-y-6">
          <Card title={`Decisions (${decs.length})`} pad={false}>
            <ul className="divide-y divide-night-600/60">{decs.map((d) => (
              <li key={d.id} className="px-5 py-3"><div className="flex items-center gap-2"><ActionBadge action={d.action} /><Outcome o={d.review_outcome} /></div><div className="mt-1 text-sm text-ink-muted">{d.rationale}</div></li>
            ))}</ul>
          </Card>
          <Card title={`Evidence recorded (${evid.length})`} pad={false}>
            <ul className="divide-y divide-night-600/60">{evid.map((e) => (
              <li key={e.id} className="px-5 py-3 text-sm">{e.claim} <Strength s={e.strength} /></li>
            ))}{!evid.length && <li className="px-5 py-4 text-sm text-ink-muted">None.</li>}</ul>
          </Card>
        </div>
      </div>
    </Page>
  );
}
