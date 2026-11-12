import { Link } from 'react-router-dom';
import { ArrowRight, Moon } from 'lucide-react';
import { supabase, DEMO } from '../lib/supabase';
import StartHere from '../components/StartHere';
import ForecastHome from '../components/ForecastHome';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, pct } from '../lib/format';
import { LOOPS, loopName } from '../lib/meta';
import { ActionBadge, Badge, Card, Err, Ladder, LoopBadge, Page, Spinner, Stat } from '../components/ui';

export default function Today() {
  const { me } = useSession();
  const since = new Date(Date.now() - 36 * 3600 * 1000).toISOString();
  const { data, error, loading } = useLoad(async () => {
    const [queue, runs, decisions, evidence, defs, stats, esc, commits] = await Promise.all([
      supabase.rpc('review_queue').then((r) => (r.error ? [] : r.data)),
      q(supabase.rpc('loop_activity')),
      q(supabase.from('decisions').select('id, loop, action, subject_type, subject_id, rationale, made_at, review_outcome').order('made_at', { ascending: false }).limit(10)),
      q(supabase.from('evidence').select('id', { count: 'exact', head: true }).gte('created_at', since).then((r: any) => ({ data: r.count, error: r.error }))),
      q(supabase.from('agent_definitions').select('id, loop, autonomy_level, max_autonomy')),
      q(supabase.from('decisions').select('loop, review_outcome').not('review_outcome', 'is', null).gte('made_at', new Date(Date.now() - 60 * 86400e3).toISOString())),
      q(supabase.from('escalations').select('*').eq('status', 'open').order('created_at', { ascending: false }).limit(5)),
      q(supabase.from('commitments').select('*').eq('status', 'open').order('due_on').limit(5)),
    ]);
    return { queue: queue as any[], runs: runs as any[], decisions: decisions as any[], evidence: evidence as number, defs: defs as any[], stats: stats as any[], esc: esc as any[], commits: commits as any[] };
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Today"><Err e={error || ''} /></Page>;
  const first = me?.name.split(' ')[0];
  const hour = new Date().getHours();
  const loopsRun = data.runs.filter((r) => Number(r.runs_36h) > 0).length;
  const runCount = data.runs.reduce((a, r) => a + Number(r.runs_36h), 0);
  const accept = (loop: string) => {
    const rows = data.stats.filter((s) => s.loop === loop);
    return rows.length ? rows.filter((r) => r.review_outcome === 'accepted').length / rows.length : null;
  };
  return (
    <Page kicker={new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
      title={<>Good {hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'}, {first}.</>}>
      {me?.role === 'manager' && <ForecastHome queue={data.queue} />}
      <div className="card relative mb-6 overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-prim/20 blur-3xl" />
        <div className="flex items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-prim/15 text-prim"><Moon size={22} /></div>
          <div>
            <div className="text-lg font-bold">Overnight, {runCount} runs across {loopsRun} loops read your data and recorded {data.evidence} new pieces of evidence.</div>
            <div className="mt-1 text-ink-muted">{data.queue.length ? <>{data.queue.length} {data.queue.length === 1 ? 'decision needs' : 'decisions need'} you. Each answer is how the loops are graded.</> : 'Nothing is waiting on you.'}</div>
            {data.queue.length > 0 && <Link to="/reviews" className="btn-primary mt-4">Open your review inbox<ArrowRight size={16} /></Link>}
          </div>
        </div>
      </div>

      {DEMO && <StartHere queue={data.queue} />}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Waiting on you" value={data.queue.length} color="#fbbf24" sub="decisions to review" />
        <Stat label="Runs last night" value={runCount} sub={`${loopsRun} of 12 loops`} />
        <Stat label="New evidence" value={data.evidence} sub="rows, each with a source" color="#a78bfa" />
        <Stat label="Open escalations" value={data.esc.length} sub="agents asked a person" color="#f472b6" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Your queue" right={<Link to="/reviews" className="text-xs font-semibold text-prim">All</Link>} pad={false}>
          <ul className="divide-y divide-night-600/60">
            {data.queue.slice(0, 6).map((d) => (
              <li key={d.decision_id}><Link to={`/reviews?d=${d.decision_id}`} className="block px-5 py-3.5 hover:bg-night-750">
                <div className="flex items-center gap-2"><LoopBadge loop={d.loop} /><ActionBadge action={d.action} /><span className="ml-auto text-xs text-ink-faint">{ago(d.made_at)}</span></div>
                <div className="mt-1.5 text-sm font-semibold">{d.subject_name}</div>
                <div className="mt-0.5 line-clamp-2 text-sm text-ink-muted">{d.rationale}</div>
              </Link></li>
            ))}
            {!data.queue.length && <li className="px-5 py-6 text-sm text-ink-muted">Inbox zero. The loops will have more by morning.</li>}
          </ul>
        </Card>
        <Card title="Loop health" right={<Link to="/loops" className="text-xs font-semibold text-prim">Loops</Link>} pad={false}>
          <ul className="divide-y divide-night-600/60">
            {LOOPS.map((l) => {
              const d = data.defs.find((x) => x.loop === l.loop);
              const a = accept(l.loop);
              return (
                <li key={l.loop}><Link to={`/loops/${l.loop}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-night-750">
                  <span className="h-2 w-2 rounded-full" style={{ background: l.color }} />
                  <span className="flex-1 truncate text-sm font-semibold">{l.name}</span>
                  {d && <Ladder level={d.autonomy_level} max={d.max_autonomy} size="sm" />}
                  <span className="w-12 text-right text-xs tabular-nums text-ink-muted">{a == null ? '—' : pct(a)}</span>
                </Link></li>
              );
            })}
          </ul>
          <div className="border-t border-night-600/60 px-5 py-2.5 text-xs text-ink-faint">Bars are the autonomy level. The percentage is how often reviewers accepted the loop's work as is.</div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Escalations: agents asking a person" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.esc.map((e) => (
            <li key={e.id} className="px-5 py-3 text-sm"><div className="text-ink">{e.reason}</div><div className="mt-1 text-xs text-ink-faint">{ago(e.created_at)}</div></li>
          ))}{!data.esc.length && <li className="px-5 py-5 text-sm text-ink-muted">None open.</li>}</ul>
        </Card>
        <Card title="Promises we made to customers" pad={false}>
          <ul className="divide-y divide-night-600/60">{data.commits.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-5 py-3 text-sm"><span className="flex-1">{c.promise}</span><Badge color={new Date(c.due_on) < new Date() ? '#f87171' : '#93a0bb'}>due {c.due_on}</Badge></li>
          ))}{!data.commits.length && <li className="px-5 py-5 text-sm text-ink-muted">None open.</li>}</ul>
        </Card>
      </div>
    </Page>
  );
}
