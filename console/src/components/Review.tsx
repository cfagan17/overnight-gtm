import { useState } from 'react';
import { Check, PencilLine, X } from 'lucide-react';
import { supabase, errText } from '../lib/supabase';
import { q, useLoad } from '../lib/hooks';
import { ago, time } from '../lib/format';
import { LEVELS } from '../lib/meta';
import { ActionBadge, Badge, Card, Err, LoopBadge, Spinner, Strength, SubjectLink, toast } from './ui';
import { PlanView } from './Plan';

const SENDERS = ['rep', 'se', 'executive', 'partner', 'agent'];

// Everything a reviewer needs to decide on one agent decision, and the three ways to answer.
export function ReviewDetail({ id, name, onDone }: { id: number; name?: string; onDone: () => void }) {
  const { data, error, loading } = useLoad(async () => {
    const d = await q(supabase.from('decisions').select('*').eq('id', id).single());
    const [ev, st, tc, run] = await Promise.all([
      q(supabase.from('decision_evidence').select('evidence(*)').eq('decision_id', id)),
      q(supabase.from('strategies').select('*').eq('decision_id', id)),
      q(supabase.from('touches').select('*').eq('decision_id', id)),
      d.run_id ? q(supabase.from('runs').select('model, prompt_version, started_at, ended_at, tokens_in, tokens_out').eq('id', d.run_id).maybeSingle()) : Promise.resolve(null),
    ]);
    let contacts: Record<number, string> = {};
    if (d.subject_type === 'company') {
      const cs = await q(supabase.from('contacts').select('id, first_name, last_name, title').eq('company_id', Number(d.subject_id)));
      contacts = Object.fromEntries((cs as any[]).map((c) => [c.id, `${c.first_name} ${c.last_name}, ${c.title}`]));
    }
    const evidence = (ev as any[]).map((r) => r.evidence).filter(Boolean).sort((a, b) => a.id - b.id);
    return { d, evidence, strategy: (st as any[])[0], touches: tc as any[], run, contacts };
  }, [id]);
  const [mode, setMode] = useState<'none' | 'edit' | 'reject'>('none');
  const [note, setNote] = useState('');
  const [sender, setSender] = useState('rep');
  const [payloadText, setPayloadText] = useState('');
  const [busy, setBusy] = useState(false);

  if (loading) return <Spinner />;
  if (error || !data) return <Err e={error || 'Not found'} />;
  const { d, evidence, strategy, touches, run, contacts } = data;
  const evIndex = Object.fromEntries(evidence.map((e: any, i: number) => [e.id, i + 1]));
  const plan = strategy?.plan;

  async function review(outcome: 'accepted' | 'edited' | 'rejected') {
    setBusy(true);
    let edited: any = null;
    if (outcome === 'edited') {
      if (plan) edited = { ...plan, sender: { type: sender, reason: note || `Changed by the reviewer to ${sender}` } };
      else { try { edited = JSON.parse(payloadText || '{}'); } catch { setBusy(false); return toast('The edited payload is not valid JSON', 'err'); } }
    }
    const { error } = await supabase.rpc('review_decision', { p_decision_id: id, p_outcome: outcome, p_note: note || null, p_edited_payload: edited });
    setBusy(false);
    if (error) return toast(errText(error), 'err');
    toast(outcome === 'accepted' ? 'Accepted. The loop is graded on this.' : outcome === 'edited' ? 'Saved your edit. The next run reads it.' : 'Rejected, with your note.');
    onDone();
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-2"><LoopBadge loop={d.loop} /><ActionBadge action={d.action} /><Badge color="#b45309">level {d.autonomy_level}: {LEVELS[d.autonomy_level]}</Badge></div>
        <div className="mt-3 text-xl font-bold"><SubjectLink type={d.subject_type} id={d.subject_id} name={name} /></div>
        <p className="mt-3 text-[15px] leading-relaxed text-ink">{d.rationale}</p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-muted">
          <span>Proposed {ago(d.made_at)}</span>
          {run && <span>Run: {run.model}, prompt {run.prompt_version}</span>}
          {run?.tokens_in && <span>{Math.round((new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s, {(run.tokens_in / 1000).toFixed(0)}k tokens in</span>}
        </div>
      </Card>

      {plan && <Card title={`Proposed plan, version ${strategy.version}`}><PlanView plan={plan} contacts={contacts} evIndex={evIndex} /></Card>}
      {d.action === 'update_field' && (
        <Card title="Proposed change"><div className="font-mono text-sm">{d.payload.table}.{d.payload.field} → <span className="text-loop">{String(d.payload.value)}</span></div></Card>
      )}
      {touches.length > 0 && (
        <Card title="Queued touch">{touches.map((t) => <div key={t.id} className="text-sm"><Badge color="#0f766e">{t.channel}</Badge> sent by <b>{t.sender_type}</b>: {t.purpose}. <span className="text-ink-muted">Status {t.status.replace('_', ' ')}</span></div>)}</Card>
      )}
      {d.payload && Object.keys(d.payload).length > 0 && !plan && d.action !== 'update_field' && (
        <Card title="What the agent proposes">
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[160px_1fr]">
            {Object.entries(d.payload).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="label pt-0.5">{k.replace(/_/g, ' ')}</dt>
                <dd>{typeof v === 'object' && v !== null ? <span className="font-mono text-xs text-ink-muted">{JSON.stringify(v)}</span> : String(v)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <Card title={`Evidence cited (${evidence.length})`} right={<span className="text-xs text-ink-faint">Strength is set by the source, not the model</span>} pad={false}>
        <ul className="divide-y divide-night-600/60">
          {evidence.map((e: any, i: number) => (
            <li key={e.id} className="flex gap-3 px-5 py-3">
              <span className="mt-0.5 font-mono text-xs font-semibold text-prim">#{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm">{e.claim}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-faint"><Strength s={e.strength} /><span>{e.kind.replace(/_/g, ' ')}</span><span className="truncate font-mono">{e.source_uri}</span><span>{time(e.observed_at)}</span></div>
              </div>
            </li>
          ))}
          {!evidence.length && <li className="px-5 py-4 text-sm text-ink-muted">No evidence cited.</li>}
        </ul>
      </Card>

      {d.review_outcome ? (
        <Card><div className="text-sm">Reviewed: <b>{d.review_outcome}</b> {ago(d.reviewed_at)}. {d.review_note}</div></Card>
      ) : (
        <div className="card sticky bottom-4 border-prim/40 p-4 ">
          {mode !== 'none' && (
            <div className="mb-3 space-y-2">
              {mode === 'edit' && plan && (
                <div className="flex flex-wrap items-center gap-2 text-sm"><span className="text-ink-muted">Sender</span>
                  {SENDERS.map((s) => <button key={s} onClick={() => setSender(s)} className={`rounded px-2.5 py-1 text-xs font-semibold ${sender === s ? 'bg-people text-night-950' : 'border border-night-600 text-ink-muted'}`}>{s}</button>)}
                </div>
              )}
              {mode === 'edit' && !plan && (
                <textarea className="input h-28 font-mono text-xs" value={payloadText || JSON.stringify(d.payload, null, 2)} onChange={(e) => setPayloadText(e.target.value)} />
              )}
              <textarea className="input h-20" placeholder={mode === 'reject' ? 'Why? The loop reads this next time.' : 'What you changed and why. The loop reads this next time.'} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {mode === 'none' ? (<>
              <button disabled={busy} className="btn-green" onClick={() => review('accepted')}><Check size={16} />Accept</button>
              <button disabled={busy} className="btn-ghost" onClick={() => setMode('edit')}><PencilLine size={16} />Edit</button>
              <button disabled={busy} className="btn-red" onClick={() => setMode('reject')}><X size={16} />Reject</button>
              <span className="ml-auto text-xs text-ink-faint">Your answer is how this loop is graded and how it earns more autonomy.</span>
            </>) : (<>
              <button disabled={busy || (mode === 'reject' && !note)} className={mode === 'reject' ? 'btn-red' : 'btn-primary'} onClick={() => review(mode === 'reject' ? 'rejected' : 'edited')}>{mode === 'reject' ? 'Reject with note' : 'Save edit'}</button>
              <button className="btn-ghost" onClick={() => { setMode('none'); setNote(''); }}>Cancel</button>
            </>)}
          </div>
        </div>
      )}
    </div>
  );
}
