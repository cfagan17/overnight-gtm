import { supabase, errText } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { day, pct } from '../lib/format';
import { Badge, Card, Empty, Err, LoopBadge, Page, Spinner } from '../components/ui';

function RangeChart({ r }: { r: any }) {
  // Difference and 95% range on a scale from -15 to +20 points.
  const lo = -0.15, hi = 0.2, x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const [a, b] = r.range_95.map(Number), d = Number(r.difference);
  return (
    <div className="relative mt-6 h-16">
      <div className="absolute left-0 right-0 top-7 h-px bg-night-600" />
      <div className="absolute top-3 h-8 w-px bg-ink-faint" style={{ left: `${x(0)}%` }} /><div className="absolute top-12 -translate-x-1/2 text-[11px] text-ink-faint" style={{ left: `${x(0)}%` }}>no effect</div>
      <div className="absolute top-6 h-2.5 rounded-full bg-prim/40" style={{ left: `${x(a)}%`, width: `${x(b) - x(a)}%` }} />
      <div className="absolute top-[18px] h-5 w-5 -translate-x-1/2 rounded-full border-4 border-night-800 bg-prim" style={{ left: `${x(d)}%` }} />
      <div className="absolute -top-1 -translate-x-1/2 text-xs font-bold text-prim" style={{ left: `${x(d)}%` }}>{d > 0 ? '+' : ''}{(d * 100).toFixed(1)} pts</div>
      <div className="absolute top-12 text-[11px] text-ink-faint" style={{ left: `${x(a)}%` }}>{(a * 100).toFixed(1)}</div>
      <div className="absolute top-12 -translate-x-full text-[11px] text-ink-faint" style={{ left: `${x(b)}%` }}>{(b * 100).toFixed(1)}</div>
    </div>
  );
}

export default function Experiments() {
  const { me } = useSession();
  const { data, error, loading } = useLoad(async () => {
    const exps = (await q(supabase.from('experiments').select('*').order('id'))) as any[];
    return Promise.all(exps.map(async (e) => {
      const r = e.status === 'draft' ? { data: null, error: null } : await supabase.rpc('experiment_result', { p_experiment_id: e.id });
      return { ...e, result: r.data, rerr: r.error ? errText(r.error) : null };
    }));
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error) return <Page title="Experiments"><Err e={error} /></Page>;
  return (
    <Page kicker="Learning without fooling ourselves" title="Experiments">
      <p className="-mt-3 mb-6 max-w-3xl text-ink-muted">Deals close for reasons a loop did not cause. So customer-facing loops are measured against a holdout: accounts fixed in advance that the agent never touches. Once an experiment starts, the database freezes who is in which group.</p>
      {!data?.length ? <Empty>No experiments yet.</Empty> : data.map((e) => (
        <Card key={e.id} className="mb-6" title={e.name} right={<div className="flex gap-2"><LoopBadge loop={e.loop} /><Badge color={e.status === 'running' ? '#34d399' : '#93a0bb'}>{e.status}</Badge></div>}>
          <p className="text-sm text-ink-muted">{e.hypothesis}. Metric: <span className="font-mono">{e.metric}</span>. {Number(e.holdout_pct)}% held out{e.starts_at ? `, started ${day(e.starts_at)}` : ''}.</p>
          {e.rerr && <div className="mt-4 text-sm text-ink-muted">{e.rerr}</div>}
          {e.result && (
            <>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {[['Agent accounts', e.result.treatment, '#a78bfa'], ['Held back', e.result.holdout, '#93a0bb']].map(([label, g, c]: any) => (
                  <div key={label} className="rounded-xl bg-night-850 p-4">
                    <div className="label">{label}</div>
                    <div className="mt-2 text-3xl font-extrabold tabular-nums" style={{ color: c }}>{pct(g.mean, 1)}</div>
                    <div className="text-sm text-ink-muted">of {g.n} accounts booked a meeting</div>
                    <div className="mt-3 flex flex-wrap gap-[3px]">{Array.from({ length: Math.min(g.n, 320) }).map((_, i) => <span key={i} className="h-1.5 w-1.5 rounded-full" style={{ background: i < Math.round(g.mean * g.n) ? c : '#2a3550' }} />)}</div>
                  </div>
                ))}
              </div>
              <RangeChart r={e.result} />
              <div className={`mt-6 rounded-xl px-4 py-3 text-sm ${e.result.conclusive ? 'bg-control/10 text-emerald-200' : 'bg-loop/10 text-amber-100'}`}>
                {e.result.conclusive ? 'The difference is real at 95% confidence.' :
                  <>Looks like a win, but with groups this small the honest answer is that we cannot tell yet. The range still includes no effect. Detecting a {(Number(e.result.difference) * 100).toFixed(0)}-point lift needs about {e.result.subjects_per_arm_needed_for_this_difference} accounts per group.</>}
              </div>
            </>
          )}
        </Card>
      ))}
    </Page>
  );
}
