import { useState } from 'react';
import { Link } from 'react-router-dom';
import { supabase, errText } from '../lib/supabase';
import { useLoad } from '../lib/hooks';
import { useSession } from '../lib/session';
import { ACTION_LABEL, loopName } from '../lib/meta';
import { Card, Err, Page, Spinner, toast } from '../components/ui';
import { Logo } from '../components/Layout';

// What each person gets in Slack each morning: integrations/slack builds this message from
// review_queue(). Accept and Reject work here exactly as they do from Slack.
export default function Slack() {
  const { me } = useSession();
  const [done, setDone] = useState<Record<number, string>>({});
  const { data, error, loading } = useLoad(async () => {
    const { data, error } = await supabase.rpc('review_queue');
    if (error) throw error;
    return data as any[];
  }, [me?.userId]);
  async function act(id: number, outcome: 'accepted' | 'rejected') {
    const { error } = await supabase.rpc('review_decision', { p_decision_id: id, p_outcome: outcome, p_note: outcome === 'rejected' ? 'Rejected from the digest' : 'Reviewed in Slack', p_edited_payload: null });
    if (error) return toast(errText(error), 'err');
    setDone((d) => ({ ...d, [id]: outcome }));
  }
  if (loading) return <Spinner />;
  if (error) return <Page title="Slack digest"><Err e={error} /></Page>;
  const items = data || [];
  return (
    <Page kicker="Where people actually work" title="The morning digest">
      <p className="-mt-3 mb-6 max-w-3xl text-ink-muted">Reps should not have to open another app. Each morning the Slack app sends every person what is waiting for them, with one-tap accept and reject. Edits open the console. This is a preview of {me?.name.split(' ')[0]}'s message, built from the same queue. The buttons are live.</p>
      <div className="mx-auto max-w-2xl">
        <div className="overflow-hidden rounded-md border border-night-600 bg-[#1a1d21] shadow-lg">
          <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5 text-sm text-white/60"><span className="font-bold text-white"># direct message</span><span>with Overnight</span></div>
          <div className="flex gap-3 p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded bg-night-800"><svg width="24" height="24" viewBox="0 0 64 64"><circle cx="34" cy="30" r="16" fill="#1d4ed8" /><circle cx="41" cy="25" r="14" fill="#18181b" /><circle cx="46" cy="44" r="3.5" fill="#b45309" /></svg></div>
            <div className="min-w-0 flex-1 text-[15px] text-[#d1d2d3]">
              <div><span className="font-bold text-white">Overnight</span> <span className="ml-1 rounded bg-white/10 px-1 text-[10px] font-bold text-white/60">APP</span> <span className="ml-1 text-xs text-white/40">7:30 AM</span></div>
              <div className="mt-1">Good morning {me?.name.split(' ')[0]}. The loops ran overnight. <b className="text-white">{items.length} {items.length === 1 ? 'thing needs' : 'things need'} you.</b></div>
              <div className="mt-3 space-y-3">
                {items.slice(0, 6).map((d) => (
                  <div key={d.decision_id} className="rounded-md border-l-4 bg-white/[.03] p-3" style={{ borderColor: '#1d4ed8' }}>
                    <div className="text-sm font-bold text-white">{ACTION_LABEL[d.action] || d.action}: {d.subject_name}</div>
                    <div className="mt-0.5 text-xs text-white/50">{loopName(d.loop)}</div>
                    <div className="mt-1.5 line-clamp-3 text-sm">{d.rationale}</div>
                    {done[d.decision_id] ? <div className="mt-2 text-sm text-emerald-300">✓ {done[d.decision_id]} by you</div> : (
                      <div className="mt-2.5 flex flex-wrap gap-2">
                        <button onClick={() => act(d.decision_id, 'accepted')} className="rounded border border-emerald-500/60 bg-emerald-600 px-3 py-1 text-sm font-semibold text-white hover:bg-emerald-500">Accept</button>
                        <Link to={`/reviews?d=${d.decision_id}`} className="rounded border border-white/20 px-3 py-1 text-sm font-semibold text-white hover:bg-white/10">Edit in console</Link>
                        <button onClick={() => act(d.decision_id, 'rejected')} className="rounded border border-white/20 px-3 py-1 text-sm font-semibold text-red-300 hover:bg-white/10">Reject</button>
                      </div>
                    )}
                  </div>
                ))}
                {!items.length && <div className="text-sm text-white/60">Nothing today. Enjoy it.</div>}
              </div>
            </div>
          </div>
        </div>
        <Card className="mt-6" title="How it is built">
          <ul className="space-y-2 text-sm text-ink-muted">
            <li><span className="font-mono text-ink">integrations/slack/digest.py</span> builds this message from <span className="font-mono text-ink">slack_review_queue()</span> for each mapped person.</li>
            <li>Button clicks call <span className="font-mono text-ink">slack_review_decision()</span>, which acts as the mapped person, so every permission check is the same as in the console.</li>
            <li>Only the service role can call those functions. A signed-in user cannot.</li>
          </ul>
        </Card>
      </div>
    </Page>
  );
}
