import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago, money } from '../lib/format';
import { STAGES } from '../lib/meta';
import { Badge, Err, Page, Spinner } from '../components/ui';

export default function Accounts() {
  const { me } = useSession();
  const [term, setTerm] = useState('');
  const { data, error, loading } = useLoad(async () => {
    const [cos, deals, terrs, sales, strats, ev] = await Promise.all([
      q(supabase.from('companies').select('id, name, segment, state_abbr, sales_id, territory_id').order('name')),
      q(supabase.from('deals').select('id, company_id, stage, amount, forecast_category').is('archived_at', null)),
      q(supabase.from('territories').select('id, name')),
      q(supabase.from('sales').select('id, first_name, last_name')),
      q(supabase.from('strategies').select('subject_id, version, status, created_at').eq('subject_type', 'company').order('version', { ascending: false })),
      q(supabase.from('evidence').select('subject_id, created_at').eq('subject_type', 'company')),
    ]);
    return { cos: cos as any[], deals: deals as any[], terrs: terrs as any[], sales: sales as any[], strats: strats as any[], ev: ev as any[] };
  }, [me?.userId]);
  const rows = useMemo(() => {
    if (!data) return [];
    const t = Object.fromEntries(data.terrs.map((x) => [x.id, x.name]));
    const s = Object.fromEntries(data.sales.map((x) => [x.id, `${x.first_name} ${x.last_name}`]));
    return data.cos.filter((c) => c.name.toLowerCase().includes(term.toLowerCase())).map((c) => {
      const d = data.deals.find((x) => x.company_id === c.id);
      const st = data.strats.find((x) => x.subject_id === String(c.id));
      const evs = data.ev.filter((x) => x.subject_id === String(c.id));
      return { ...c, terr: t[c.territory_id], owner: s[c.sales_id], deal: d, plan: st, evCount: evs.length, lastEv: evs.map((x) => x.created_at).sort().pop() };
    });
  }, [data, term]);
  if (loading) return <Spinner />;
  if (error) return <Page title="Accounts"><Err e={error} /></Page>;
  return (
    <Page kicker="Layer 1, the ledger" title="Accounts" actions={
      <div className="relative"><Search size={15} className="absolute left-3 top-2.5 text-ink-faint" /><input className="input w-64 pl-9" placeholder="Search accounts" value={term} onChange={(e) => setTerm(e.target.value)} /></div>}>
      <div className="mb-3 text-sm text-ink-muted">{rows.length} accounts you can see. Row-level security decides which: a rep sees their own and their territory's, a manager their team's, Rev Ops everything.</div>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead><tr className="border-b border-night-600/60 text-left">{['Account', 'Territory', 'Owner', 'Open deal', 'Latest plan', 'Evidence'].map((h) => <th key={h} className="label px-5 py-3">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-night-600/50">
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-night-750">
                <td className="px-5 py-3"><Link to={`/accounts/${r.id}`} className="font-semibold hover:text-prim">{r.name}</Link><div className="text-xs text-ink-faint">{r.segment}, {r.state_abbr}</div></td>
                <td className="px-5 py-3 text-ink-muted">{r.terr || '—'}</td>
                <td className="px-5 py-3 text-ink-muted">{r.owner || '—'}</td>
                <td className="px-5 py-3">{r.deal ? <><span className="font-semibold tabular-nums">{money(r.deal.amount)}</span> <span className="text-ink-muted">{STAGES.find((s) => s.id === r.deal.stage)?.name}</span></> : '—'}</td>
                <td className="px-5 py-3">{r.plan ? <Badge color={r.plan.status === 'proposed' ? '#b45309' : r.plan.status === 'rejected' ? '#b91c1c' : '#047857'}>v{r.plan.version} {r.plan.status}</Badge> : <span className="text-ink-faint">none</span>}</td>
                <td className="px-5 py-3 text-ink-muted">{r.evCount} <span className="text-ink-faint">{r.lastEv ? `· ${ago(r.lastEv)}` : ''}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}
