import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { useSession } from '../lib/session';
import { toast } from './ui';

const MAYA = 'ana.rep@northwind.example';
const KEY = 'overnight-start-here-dismissed';
const isAcmePlan = (d: any) => d.subject_name === 'Acme Orchards' && d.action === 'propose_strategy';

// Demo only: three places a first-time visitor should see, each one click away. It holds no
// data of its own. The Acme plan is looked up in the review queue the database returns.
export default function StartHere({ queue }: { queue: any[] }) {
  const nav = useNavigate();
  const { signInAs } = useSession();
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(KEY) === '1'; } catch { return false; } });
  const [busy, setBusy] = useState(false);
  if (hidden) return null;
  const acme = queue.find(isAcmePlan);

  // The plan waits in Maya's inbox. Anyone else is switched to Maya first, the same as picking
  // her in the person switcher.
  async function openAcme() {
    if (acme) return nav(`/reviews?d=${acme.decision_id}`);
    setBusy(true);
    const err = await signInAs(MAYA);
    if (err) { setBusy(false); return toast(err, 'err'); }
    nav('/reviews?for=Acme%20Orchards');
  }

  const stops = [
    { n: 1, title: 'The Acme Orchards account plan', note: 'Written by Claude. Every claim cites its evidence, and it kept the sender Maya chose in her last edit.',
      cta: acme ? 'Open the plan' : 'Open it as Maya Chen', go: openAcme },
    { n: 2, title: "The forecast loop's call, next to the human one", note: 'The loop only observes here. Nobody acts on its number until its record earns that.',
      cta: 'Open the pipeline', go: () => nav('/pipeline') },
    { n: 3, title: 'How outreach earned trust, then lost some', note: 'Promoted on its review record, then demoted after one policy violation. Every step is on the record.',
      cta: 'Open the loop', go: () => nav('/loops/outreach') },
  ];
  return (
    <section className="card mb-6 p-4" aria-label="Start here">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="label">Start here: three things worth a minute each</div>
        <button aria-label="Dismiss" title="Dismiss" className="text-ink-faint hover:text-ink"
          onClick={() => { try { localStorage.setItem(KEY, '1'); } catch { /* private mode */ } setHidden(true); }}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {stops.map((s) => (
          <button key={s.n} disabled={busy} onClick={s.go} className="rounded-md bg-night-850 p-4 text-left hover:bg-night-750 disabled:opacity-60">
            <div className="flex items-baseline gap-2"><span className="text-xs font-bold text-prim">{s.n}</span><span className="text-sm font-bold">{s.title}</span></div>
            <div className="mt-1 text-sm text-ink-muted">{s.note}</div>
            <div className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-prim">{s.cta}<ArrowRight size={13} /></div>
          </button>
        ))}
      </div>
    </section>
  );
}
