import { Badge } from './ui';

type Ev = { id: number };
const Cite = ({ ids, evIndex }: { ids?: number[]; evIndex?: Record<number, number> }) =>
  ids?.length ? (
    <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((i) => <span key={i} className="rounded-md bg-prim/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-prim">#{evIndex?.[i] ?? i}</span>)}
    </span>
  ) : null;

// Renders an account plan (the account-plan skill's output shape), or a simple fallback.
export function PlanView({ plan, contacts = {}, evIndex }: { plan: any; contacts?: Record<number, string>; evIndex?: Record<number, number> }) {
  if (!plan) return null;
  if (!plan.why_now || typeof plan.why_now === 'string') {
    return (
      <div className="space-y-2 text-sm">
        {plan.summary && <div className="font-semibold">{plan.summary}</div>}
        {plan.sender && <div><span className="text-ink-muted">Sender </span><Badge color="#be185d">{plan.sender.type}</Badge></div>}
      </div>
    );
  }
  const Section = ({ title, children }: any) => (
    <div className="border-t border-night-600/60 py-4 first:border-t-0 first:pt-0">
      <div className="label mb-2">{title}</div>{children}
    </div>
  );
  return (
    <div className="text-sm leading-relaxed">
      <Section title="Why now">
        <ul className="space-y-1.5">{plan.why_now.map((w: any, i: number) => <li key={i}>{w.claim}<Cite ids={w.evidence} evIndex={evIndex} /></li>)}</ul>
      </Section>
      {plan.entry_points && (
        <Section title="Who">
          <ul className="space-y-2.5">{plan.entry_points.map((e: any, i: number) => (
            <li key={i}><span className="font-semibold">{contacts[e.contact_id] || `Contact ${e.contact_id}`}. </span><span className="text-ink-muted">{e.reason}</span><Cite ids={e.evidence} evIndex={evIndex} /></li>
          ))}</ul>
        </Section>
      )}
      {plan.sender && (
        <Section title="Sender">
          <div className="flex flex-wrap items-baseline gap-2"><Badge color="#be185d" solid>{plan.sender.type}</Badge><span className="text-ink-muted">{plan.sender.reason}</span></div>
        </Section>
      )}
      {plan.channel_and_sequence && (
        <Section title="Sequence">
          <ol className="space-y-2.5">{plan.channel_and_sequence.map((s: any) => {
            const c = plan.content?.find((x: any) => x.step === s.step);
            return (
              <li key={s.step} className="flex gap-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-night-700 text-xs font-bold">{s.step}</span>
                <div><Badge color="#0f766e">{s.channel}</Badge> <span>{s.purpose}</span>
                  {c && <div className="mt-1 text-ink-muted">{c.carries}<Cite ids={c.evidence} evIndex={evIndex} /></div>}</div>
              </li>
            );
          })}</ol>
        </Section>
      )}
      {plan.risks && (
        <Section title="Risks">
          <ul className="space-y-1.5">{plan.risks.map((r: string, i: number) => <li key={i} className={i === 0 ? 'rounded bg-loop/10 px-3 py-2 text-amber-800' : 'text-ink-muted'}>{r}</li>)}</ul>
        </Section>
      )}
      {plan.what_would_change_it && <Section title="What would change it"><div className="text-ink-muted">{plan.what_would_change_it}</div></Section>}
    </div>
  );
}
