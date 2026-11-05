import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ago } from '../lib/format';
import { ActionBadge, Empty, Err, LoopBadge, Page, Spinner } from '../components/ui';
import { ReviewDetail } from '../components/Review';

export default function Reviews() {
  const { me } = useSession();
  const [params, setParams] = useSearchParams();
  const { data, error, loading, reload } = useLoad(async () => {
    const { data, error } = await supabase.rpc('review_queue');
    if (error) throw error;
    return data as any[];
  }, [me?.userId]);
  const sel = Number(params.get('d')) || data?.[0]?.decision_id;
  useEffect(() => { if (data?.length && !params.get('d')) setParams({ d: String(data[0].decision_id) }, { replace: true }); }, [data]); // eslint-disable-line

  if (loading && !data) return <Spinner />;
  if (error) return <Page title="Review inbox"><Err e={error} /></Page>;
  const items = data || [];
  const current = items.find((x) => x.decision_id === sel);
  return (
    <Page kicker="People in the loop" title="Review inbox">
      {me?.role === 'readonly' && <div className="mb-4 text-sm text-ink-muted">Read-only users see everything but do not review.</div>}
      {!items.length ? <Empty>Nothing is waiting on you. Every decision the loops made overnight has been reviewed.</Empty> : (
        <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
          <div className="card h-fit overflow-hidden lg:sticky lg:top-6">
            <div className="border-b border-night-600/60 px-4 py-3 text-xs text-ink-muted">{items.length} waiting, oldest first</div>
            <ul className="max-h-[70vh] divide-y divide-night-600/60 overflow-y-auto">
              {items.map((d) => (
                <li key={d.decision_id}>
                  <button onClick={() => setParams({ d: String(d.decision_id) })}
                    className={`block w-full px-4 py-3.5 text-left transition ${d.decision_id === sel ? 'bg-night-700 shadow-[inset_3px_0_0_#a78bfa]' : 'hover:bg-night-750'}`}>
                    <div className="flex items-center gap-2"><LoopBadge loop={d.loop} /><span className="ml-auto text-xs text-ink-faint">{ago(d.made_at)}</span></div>
                    <div className="mt-1.5 flex items-center gap-2 text-sm font-semibold">{d.subject_name}<ActionBadge action={d.action} /></div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{d.rationale}</div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div>{current ? <ReviewDetail key={current.decision_id} id={current.decision_id} name={current.subject_name}
            onDone={() => { setParams({}); reload(); }} /> : <Empty>Pick a decision.</Empty>}</div>
        </div>
      )}
    </Page>
  );
}
