import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { pct } from '../lib/format';
import { loopName, LOOPS } from '../lib/meta';
import { Badge, Bar, Card, Err, LoopBadge, Page, Spinner, Strength } from '../components/ui';

export default function Insights() {
  const { me } = useSession();
  const { data, error, loading } = useLoad(async () => {
    const [ev, ov, mp] = await Promise.all([
      q(supabase.from('insight_evidence_in_reviews').select('*')),
      q(supabase.from('insight_overrides').select('*').order('override_rate', { ascending: false })),
      q(supabase.from('insight_model_performance').select('*')),
    ]);
    return { ev: ev as any[], ov: ov as any[], mp: mp as any[] };
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Insights"><Err e={error || ''} /></Page>;
  const models = Array.from(new Set(data.mp.map((m) => m.model))).sort();
  const byLoopModel = (loop: string, model: string) => {
    const rows = data.mp.filter((m) => m.loop === loop && m.model === model && m.accepted_as_is != null);
    const n = rows.reduce((a, r) => a + Number(r.decisions), 0);
    return n >= 5 ? rows.reduce((a, r) => a + Number(r.accepted_as_is) * Number(r.decisions), 0) / n : null;   // fewer than 5 reviews says nothing
  };
  return (
    <Page kicker="The primitives are a data foundation" title="Insights">
      <p className="-mt-3 mb-6 max-w-3xl text-ink-muted">Every answer here is a plain SQL view over the primitives, filtered by your own access. The same queries are in the repo under <span className="font-mono text-ink">examples/queries</span>, for anyone to run or hand to an AI.</p>
      <Card title="Did the model upgrade help? Accepted as is, by loop and model" className="mb-6">
        <div className="mb-4 flex gap-4 text-xs">{models.map((m, i) => <span key={m} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: i ? '#a78bfa' : '#5d6985' }} /><span className="font-mono">{m}</span></span>)}</div>
        {!models.length && <div className="text-sm text-ink-muted">Run history is visible to owners, managers and read-only users. Switch to Sam or Morgan to see how each model did.</div>}
        <div className="space-y-3">{LOOPS.map((l) => {
          const vals = models.map((m) => byLoopModel(l.loop, m));
          if (vals.every((v) => v == null)) return null;
          return (
            <div key={l.loop} className="grid grid-cols-[180px_1fr] items-center gap-4">
              <div className="truncate text-sm font-semibold">{l.name}</div>
              <div className="space-y-1">{vals.map((v, i) => (
                <div key={i} className="flex items-center gap-2"><div className="h-2.5 flex-1 rounded-full bg-night-700"><div className="h-2.5 rounded-full" style={{ width: `${(v || 0) * 100}%`, background: i ? '#a78bfa' : '#5d6985' }} /></div><span className="w-14 text-right text-xs tabular-nums text-ink-muted">{v == null ? 'too few' : pct(v)}</span></div>
              ))}</div>
            </div>
          );
        })}</div>
      </Card>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Where people keep overriding the agents" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.ov.slice(0, 10).map((o, i) => (
            <li key={i} className="px-5 py-3">
              <div className="flex items-center gap-2"><LoopBadge loop={o.loop} /><span className="text-xs text-ink-faint">{o.action.replace(/_/g, ' ')}</span><span className="ml-auto text-sm font-bold tabular-nums text-loop">{pct(o.override_rate)}</span></div>
              <div className="mt-1 text-xs text-ink-faint">{o.reviewed} reviewed</div>
              {o.recent_notes?.length > 0 && <div className="mt-2 space-y-1">{o.recent_notes.slice(0, 2).map((n: string, j: number) => <div key={j} className="text-sm text-ink-muted">“{n}”</div>)}</div>}
            </li>
          ))}</ul>
        </Card>
        <Card title="Which evidence shows up in plans people accept" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.ev.sort((a, b) => (b.in_accepted + b.in_edited + b.in_rejected) - (a.in_accepted + a.in_edited + a.in_rejected)).map((e, i) => {
            const t = e.in_accepted + e.in_edited + e.in_rejected;
            return (
              <li key={i} className="px-5 py-3">
                <div className="flex items-center gap-2 text-sm"><span className="font-semibold">{e.kind.replace(/_/g, ' ')}</span><Strength s={e.strength} /><span className="ml-auto text-xs tabular-nums text-ink-muted">{pct(e.in_accepted / t)} accepted, {t} uses</span></div>
                <div className="mt-2"><Bar parts={[{ v: e.in_accepted, c: '#34d399' }, { v: e.in_edited, c: '#fbbf24' }, { v: e.in_rejected, c: '#f87171' }]} /></div>
              </li>
            );
          })}</ul>
        </Card>
      </div>
    </Page>
  );
}
