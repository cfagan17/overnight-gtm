import { Link } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { money, ago } from '../lib/format';
import { STAGES } from '../lib/meta';
import { Avatar, Badge, Card, Err, Page, Spinner } from '../components/ui';

export default function Pipeline() {
  const { me } = useSession();
  const { data, error, loading } = useLoad(async () => {
    const [deals, cos, sales, terrs, calls, flags] = await Promise.all([
      q(supabase.from('deals').select('id, name, company_id, stage, amount, forecast_category, expected_closing_date, sales_id, territory_id').is('archived_at', null)),
      q(supabase.from('companies').select('id, name')),
      q(supabase.from('sales').select('id, first_name, last_name')),
      q(supabase.from('territories').select('id, name')),
      q(supabase.from('evidence').select('subject_id, claim, observed_at').eq('subject_type', 'territory').eq('kind', 'inferred').like('claim', 'Agent forecast call%').order('observed_at', { ascending: false })),
      q(supabase.from('decisions').select('subject_id, rationale').eq('loop', 'deal_inspection').eq('action', 'flag_risk').is('review_outcome', null)),
    ]);
    return { deals: deals as any[], cos: cos as any[], sales: sales as any[], terrs: terrs as any[], calls: calls as any[], flags: flags as any[] };
  }, [me?.userId]);
  if (loading) return <Spinner />;
  if (error || !data) return <Page title="Pipeline"><Err e={error || ''} /></Page>;
  const co = Object.fromEntries(data.cos.map((c) => [c.id, c.name]));
  const sname = Object.fromEntries(data.sales.map((s) => [s.id, `${s.first_name} ${s.last_name}`]));
  const open = data.deals.filter((d) => !['won', 'lost'].includes(d.stage));
  const byCat = (c: string) => open.filter((d) => d.forecast_category === c).reduce((a, d) => a + Number(d.amount), 0);
  const latestCalls = data.terrs.map((t) => ({ t, call: data.calls.find((c) => c.subject_id === String(t.id)) })).filter((x) => x.call);
  const risky = new Set(data.flags.map((f) => f.subject_id));
  return (
    <Page kicker="Layer 1, the ledger" title="Pipeline">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[['commit', '#047857'], ['best_case', '#0f766e'], ['pipeline', '#52525b'], ['omitted', '#71717a']].map(([c, col]) => (
          <div key={c} className="card p-5"><div className="label">{c.replace('_', ' ')}</div><div className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: col }}>{money(byCat(c))}</div></div>
        ))}
      </div>
      {latestCalls.length > 0 && (
        <Card className="mt-6" title="The forecast loop's independent call, next to the human one" right={<Badge color="#b45309">level 0: observe only</Badge>}>
          <div className="grid gap-3 md:grid-cols-2">{latestCalls.map(({ t, call }) => (
            <div key={t.id} className="rounded-md bg-night-850 p-4"><div className="text-sm font-bold">{t.name}</div><div className="mt-1 text-sm text-ink-muted">{call.claim.replace('Agent forecast call: ', 'Agent: ')}</div><div className="mt-1 text-xs text-ink-faint">{ago(call.observed_at)}</div></div>
          ))}</div>
        </Card>
      )}
      {/* Five columns side by side from 1280px wide. Narrower than that, they scroll sideways. */}
      <div className="mt-6 grid grid-flow-col auto-cols-[minmax(230px,1fr)] gap-3 overflow-x-auto pb-2 xl:grid-flow-row xl:auto-cols-auto xl:grid-cols-5 xl:overflow-visible">
        {STAGES.map((s) => {
          const ds = data.deals.filter((d) => d.stage === s.id);
          return (
            <div key={s.id} className="min-w-0">
              <div className="mb-3 flex items-baseline justify-between px-1"><div className="text-sm font-bold">{s.name}</div><div className="text-xs tabular-nums text-ink-muted">{ds.length} · {money(ds.reduce((a, d) => a + Number(d.amount), 0))}</div></div>
              <div className="space-y-3">{ds.map((d) => (
                <Link key={d.id} to={`/accounts/${d.company_id}`} className="card card-hover block p-4">
                  <div className="truncate text-sm font-semibold">{co[d.company_id]}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">{money(d.amount)}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5"><Badge color="#52525b">{d.forecast_category}</Badge>{risky.has(String(d.id)) && <Badge color="#b91c1c">risk flagged</Badge>}</div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-ink-muted"><Avatar name={sname[d.sales_id] || '?'} size={20} /><span className="truncate">{sname[d.sales_id]}</span><span className="ml-auto whitespace-nowrap">{d.expected_closing_date}</span></div>
                </Link>
              ))}</div>
            </div>
          );
        })}
      </div>
    </Page>
  );
}
