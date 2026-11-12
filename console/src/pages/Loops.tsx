import { Link } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, pct } from '../lib/format';
import { LEVELS, LOOPS } from '../lib/meta';
import { Badge, Bar, Err, Ladder, Page, Spinner } from '../components/ui';

export default function Loops() {
  const { me } = useSession();
  const { data, error, loading } = useLoad(async () => {
    const [defs, decs, runs, replay, viol, prompts] = await Promise.all([
      q(supabase.from('agent_definitions').select('*')),
      q(supabase.from('decisions').select('loop, review_outcome').gte('made_at', new Date(Date.now() - 60 * 86400e3).toISOString())),
      q(supabase.rpc('loop_activity')),
      q(supabase.from('replay_results').select('agent_definition_id, model, score, run_at').order('run_at', { ascending: false })),
      q(supabase.from('policy_violations').select('agent_definition_id, flagged_at')),
      q(supabase.from('loop_prompts').select('loop, version, status')),
    ]);
    return { defs: defs as any[], decs: decs as any[], runs: runs as any[], replay: replay as any[], viol: viol as any[], prompts: prompts as any[] };
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Loops"><Err e={error || ''} /></Page>;
  return (
    <Page kicker="Layer 4" title="The loops" actions={<div className="text-sm text-ink-muted">One loop for each thing a great Rev Ops team does.</div>}>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {LOOPS.map((l) => {
          const d = data.defs.find((x) => x.loop === l.loop);
          const ds = data.decs.filter((x) => x.loop === l.loop && x.review_outcome);
          const n = (o: string) => ds.filter((x) => x.review_outcome === o).length;
          const last = data.runs.find((r) => r.loop === l.loop);
          const rp = d && data.replay.find((r) => r.agent_definition_id === d.id);
          const v = d && data.viol.filter((x) => x.agent_definition_id === d.id && +new Date(x.flagged_at) > Date.now() - 60 * 86400e3).length;
          const pending = data.prompts.filter((p) => p.loop === l.loop && p.status === 'proposed').length;
          return (
            <Link key={l.loop} to={`/loops/${l.loop}`} className="card card-hover group relative overflow-hidden p-5">
              <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: l.color }} />
              <div className="flex items-start justify-between gap-3">
                <div><div className="label" style={{ color: l.color }}>{l.area}</div><div className="mt-1 text-lg font-bold">{l.name}</div></div>
                <Badge color="#52525b">{l.cadence}</Badge>
              </div>
              <p className="mt-2 text-sm text-ink-muted">{l.job}</p>
              {d && <div className="mt-4 flex items-center justify-between"><Ladder level={d.autonomy_level} max={d.max_autonomy} /><span className="text-xs font-semibold text-loop">{LEVELS[d.autonomy_level]}</span></div>}
              <div className="mt-4"><Bar parts={[{ v: n('accepted'), c: '#047857', label: 'accepted' }, { v: n('edited'), c: '#b45309', label: 'edited' }, { v: n('rejected'), c: '#b91c1c', label: 'rejected' }]} /></div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
                <span>{ds.length} reviewed, {ds.length ? pct(n('accepted') / ds.length) : '—'} as is</span>
                {rp && <span>replay {Number(rp.score).toFixed(2)}</span>}
                <span>last run {ago(last?.last_run_at)}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {d && d.max_autonomy <= 2 && <Badge color="#be185d">capped at 2: needs a human signature</Badge>}
                {v ? <Badge color="#b91c1c">{v} violation, 60 days</Badge> : null}
                {pending ? <Badge color="#1d4ed8">prompt edit waiting</Badge> : null}
              </div>
            </Link>
          );
        })}
      </div>
    </Page>
  );
}
