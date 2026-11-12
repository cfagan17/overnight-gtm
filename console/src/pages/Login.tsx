import { useState } from 'react';
import { ArrowRight, Github } from 'lucide-react';
import { useSession } from '../lib/session';
import { DEMO } from '../lib/supabase';
import { PERSONAS } from '../lib/meta';
import { Avatar } from '../components/ui';
import { Logo } from '../components/Layout';

export default function Login() {
  const { signInAs } = useSession();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const go = async (e: string, p?: string) => { setBusy(e); setErr(await signInAs(e, p)); setBusy(null); };

  return (
    <div className="relative min-h-full">
      <div className="relative mx-auto max-w-6xl px-5 py-10 sm:py-16">
        <div className="flex items-center justify-between"><Logo />
          <a className="btn-ghost" href="https://github.com/cfagan17/overnight-gtm" target="_blank" rel="noreferrer"><Github size={16} />GitHub</a></div>
        <div className="mt-14 max-w-3xl">
          <div className="label mb-4">The open-source AI operating layer for go to market</div>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-[44px] sm:leading-[1.1]">Your GTM loops ran overnight.<br /><span className="text-ink-muted">Here is what they decided, and why.</span></h1>
          <p className="mt-5 max-w-2xl text-base text-ink-muted">Twelve agent loops read every account, call and signal each night, record their reasoning as evidence and decisions, and earn autonomy only as fast as people's reviews allow. Pick a person to see the system the way they do. Row-level security decides what each one sees.</p>
        </div>
        {DEMO ? (
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PERSONAS.map((p) => (
              <button key={p.email} onClick={() => go(p.email)} disabled={!!busy}
                className="card card-hover group p-5 text-left">
                <div className="flex items-center gap-3"><Avatar name={p.name} color={p.color} size={44} />
                  <div><div className="text-base font-semibold">{p.name}</div><div className="text-sm text-ink-muted">{p.role}</div></div></div>
                <p className="mt-4 text-sm text-ink-muted">{p.see}</p>
                <div className="mt-4 flex items-center gap-1.5 text-sm font-semibold text-prim">{busy === p.email ? 'Signing in…' : 'Sign in as ' + p.name.split(' ')[0]}<ArrowRight size={15} className="transition group-hover:translate-x-1" /></div>
              </button>
            ))}
          </div>
        ) : (
          <form className="card mt-12 max-w-md space-y-3 p-6" onSubmit={(e) => { e.preventDefault(); go(email, pw); }}>
            <input className="input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className="input" type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} />
            <button className="btn-primary w-full justify-center">Sign in</button>
          </form>
        )}
        {err && <div className="mt-4 text-sm text-red-700">{err}</div>}
        <p className="mt-10 text-xs text-ink-faint">Demo data for a fictional company, Northwind Data. Anything you do here is real in the demo database and is reset regularly.</p>
      </div>
    </div>
  );
}
