import { Link } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { ago, money } from '../lib/format';
import { STAGES } from '../lib/meta';
import { Badge, Card } from './ui';

const stageName = (id: string) => STAGES.find((s) => s.id === id)?.name || id;
const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${money(Math.abs(n))}`;

// The top of Today for a sales leader: the forecast loop's call against the human call, then
// the deals the inspection loop flagged. Everything shown is read as the signed-in person, so
// row-level security decides what is here. The numbers and the gap come from the
// public.forecast_calls view; this component only lays them out.
export default function ForecastHome({ queue }: { queue: any[] }) {
  const { data } = useLoad(async () => {
    const [calls, flags, deals] = await Promise.all([
      supabase.from('forecast_calls').select('*').order('territory_id').then((r) => (r.error ? [] : r.data)),
      q(supabase.from('decisions').select('id, subject_id, rationale, payload, made_at').eq('loop', 'deal_inspection').eq('action', 'flag_risk')
        .is('review_outcome', null).order('made_at', { ascending: false })),
      q(supabase.from('deals').select('id, name, amount, stage, company_id, expected_closing_date').is('archived_at', null)),
    ]);
    const ids = (flags as any[]).map((f) => f.id);
    const ev = ids.length ? await q(supabase.from('decision_evidence').select('decision_id, evidence(id, kind, claim)').in('decision_id', ids)) : [];
    return { calls: calls as any[], flags: flags as any[], deals: deals as any[], ev: ev as any[] };
  }, []);
  if (!data) return null;
  const deal = Object.fromEntries(data.deals.map((d) => [String(d.id), d]));
  const flagged = data.flags.filter((f) => deal[f.subject_id]).sort((a, b) => Number(deal[b.subject_id].amount) - Number(deal[a.subject_id].amount));
  const inQueue = new Set(queue.map((d) => d.decision_id));
  const withNumbers = data.calls.filter((c) => c.agent_call_usd != null && c.human_call_usd != null);
  const sum = (k: string) => withNumbers.reduce((a, c) => a + Number(c[k]), 0);

  return (
    <div className="mb-6 grid gap-6 xl:grid-cols-[1fr_1.15fr]">
      <Card title="Forecast: the loop's call against the human call" right={<Badge color="#b45309">the loop only observes</Badge>} pad={false}>
        {!data.calls.length ? <div className="px-5 py-6 text-sm text-ink-muted">No forecast call is visible to you yet.</div> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-ink-faint">
              <th className="px-5 py-2.5 font-semibold">Territory</th><th className="px-3 py-2.5 text-right font-semibold">Loop</th>
              <th className="px-3 py-2.5 text-right font-semibold">Human</th><th className="px-5 py-2.5 text-right font-semibold">Gap</th>
            </tr></thead>
            <tbody className="divide-y divide-night-600/60">
              {data.calls.map((c) => (
                <tr key={c.territory_id} title={c.claim}>
                  <td className="px-5 py-3"><div className="font-semibold">{c.territory}</div><div className="text-xs text-ink-faint">{ago(c.observed_at)}</div></td>
                  <td className="px-3 py-3 text-right tabular-nums">{money(c.agent_call_usd)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{money(c.human_call_usd)}</td>
                  <td className="px-5 py-3 text-right font-bold tabular-nums" style={{ color: c.gap_usd == null ? undefined : Number(c.gap_usd) < 0 ? '#b91c1c' : '#047857' }}>
                    {c.gap_usd == null ? '—' : signed(Number(c.gap_usd))}</td>
                </tr>
              ))}
              {withNumbers.length > 1 && (
                <tr className="bg-night-850 font-bold">
                  <td className="px-5 py-3">All {withNumbers.length}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{money(sum('agent_call_usd'))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{money(sum('human_call_usd'))}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{signed(sum('gap_usd'))}</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <div className="border-t border-night-600/60 px-5 py-2.5 text-xs text-ink-faint">Gap is the loop's call minus the human call, this quarter. <Link to="/pipeline" className="font-semibold text-prim">Pipeline</Link></div>
      </Card>

      <Card title={`Deals flagged at risk${flagged.length ? ` (${flagged.length})` : ''}`} right={<Link to="/loops/deal_inspection" className="text-xs font-semibold text-prim">Deal inspection</Link>} pad={false}>
        <ul className="max-h-[420px] divide-y divide-night-600/60 overflow-y-auto">
          {flagged.map((f) => {
            const d = deal[f.subject_id];
            const ev = data.ev.filter((e) => e.decision_id === f.id && e.evidence).map((e) => e.evidence);
            return (
              <li key={f.id}><Link to={inQueue.has(f.id) ? `/reviews?d=${f.id}` : `/accounts/${d.company_id}`} className="block px-5 py-3.5 hover:bg-night-750">
                <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-bold">{d.name}</span><span className="text-sm tabular-nums text-ink-muted">{money(d.amount)}</span>
                  <Badge color="#52525b">{stageName(d.stage)}</Badge><span className="ml-auto text-xs text-ink-faint">{ago(f.made_at)}</span></div>
                <div className="mt-1 text-sm text-ink">{f.payload?.risk || f.rationale}</div>
                {ev.map((e: any) => <div key={e.id} className="mt-1 text-xs text-ink-muted"><span className="text-ink-faint">{String(e.kind).replace(/_/g, ' ')}:</span> {e.claim}</div>)}
              </Link></li>
            );
          })}
          {!flagged.length && <li className="px-5 py-6 text-sm text-ink-muted">No open risk flags on deals you can see.</li>}
        </ul>
      </Card>
    </div>
  );
}
