import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Activity, BarChart3, BookOpen, Building2, FlaskConical, Inbox, KanbanSquare, LogOut, Menu, MessageSquare, Repeat2, ScrollText, Shield, Sun, X } from 'lucide-react';
import { useSession } from '../lib/session';
import { supabase } from '../lib/supabase';
import { PERSONAS } from '../lib/meta';
import { Avatar } from './ui';

const NAV = [
  { to: '/', label: 'Today', icon: Sun },
  { to: '/reviews', label: 'Review inbox', icon: Inbox, badge: true },
  { to: '/accounts', label: 'Accounts', icon: Building2 },
  { to: '/pipeline', label: 'Pipeline', icon: KanbanSquare },
  { sep: 'The loops' },
  { to: '/loops', label: 'Loops', icon: Repeat2 },
  { to: '/runs', label: 'Runs', icon: Activity },
  { to: '/experiments', label: 'Experiments', icon: FlaskConical },
  { to: '/insights', label: 'Insights', icon: BarChart3 },
  { sep: 'Control' },
  { to: '/policies', label: 'Policies and grants', icon: Shield },
  { to: '/audit', label: 'Audit log', icon: ScrollText },
  { sep: 'Where people work' },
  { to: '/slack', label: 'Slack digest', icon: MessageSquare },
  { to: '/about', label: 'About this console', icon: BookOpen },
] as const;

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="30" height="30" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#141b2e" /><circle cx="34" cy="30" r="16" fill="#a78bfa" /><circle cx="41" cy="25" r="14" fill="#141b2e" /><circle cx="46" cy="44" r="3.5" fill="#fbbf24" /></svg>
      <div className="leading-none"><div className="text-[17px] font-extrabold tracking-tight">Overnight</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-faint">console</div></div>
    </div>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { me, signOut, signInAs } = useSession();
  const [queue, setQueue] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => { setOpen(false); }, [loc.pathname]);
  useEffect(() => {
    supabase.rpc('review_queue').then(({ data }) => setQueue(Array.isArray(data) ? data.length : null));
  }, [loc.pathname, me?.userId]);
  const persona = PERSONAS.find((p) => p.email === me?.email);

  const side = (
    <nav className="flex h-full flex-col gap-0.5 p-3">
      <div className="px-2 pb-5 pt-2"><Logo /></div>
      {NAV.map((n, i) => 'sep' in n ? (
        <div key={i} className="label px-3 pb-1.5 pt-5">{n.sep}</div>
      ) : (
        <NavLink key={n.to} to={n.to} end={n.to === '/'}
          className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition ${isActive ? 'bg-night-700 text-ink shadow-[inset_2px_0_0_#a78bfa]' : 'text-ink-muted hover:bg-night-800 hover:text-ink'}`}>
          <n.icon size={17} />
          <span className="flex-1">{n.label}</span>
          {'badge' in n && queue ? <span className="rounded-full bg-loop px-2 py-0.5 text-[11px] font-bold text-night-950">{queue}</span> : null}
        </NavLink>
      ))}
      <div className="mt-auto pt-6">
        <div className="card p-3">
          <div className="flex items-center gap-3">
            <Avatar name={me?.name || '?'} color={persona?.color} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold">{me?.name}</div>
              <div className="truncate text-xs text-ink-muted">{persona?.role || me?.role}</div>
            </div>
            <button title="Sign out" onClick={() => { signOut(); nav('/'); }} className="rounded-lg p-1.5 text-ink-faint hover:bg-night-700 hover:text-ink"><LogOut size={16} /></button>
          </div>
          <button onClick={() => setSwitching((s) => !s)} className="mt-3 w-full rounded-lg border border-night-600 px-2 py-1.5 text-xs font-semibold text-ink-muted hover:text-ink">Switch person</button>
          {switching && (
            <div className="mt-2 flex flex-col gap-1">
              {PERSONAS.filter((p) => p.email !== me?.email).map((p) => (
                <button key={p.email} onClick={async () => { setSwitching(false); await signInAs(p.email); nav('/'); }}
                  className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-night-700">
                  <Avatar name={p.name} color={p.color} size={22} /><span className="font-semibold">{p.name}</span><span className="truncate text-ink-faint">{p.role}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 overflow-y-auto border-r border-night-700 bg-night-950/60 lg:block">{side}</aside>
      {open && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-50 w-72 overflow-y-auto border-r border-night-700 bg-night-950 transition-transform lg:hidden ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <button className="absolute right-3 top-3 p-2 text-ink-muted" onClick={() => setOpen(false)}><X size={18} /></button>{side}
      </aside>
      <main className="min-w-0 flex-1">
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-night-700 bg-night-900/80 px-4 py-3 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(true)} className="p-1.5 text-ink-muted"><Menu size={20} /></button><Logo />
        </div>
        <div className="border-b border-night-700 bg-gradient-to-r from-prim/10 via-transparent to-loop/10 px-4 py-2 text-center text-xs text-ink-muted sm:px-8">
          Demo data for a fictional company, Northwind Data. Day to day, people review in Slack and agents work in the database. This console is the window onto all of it.
        </div>
        {children}
      </main>
    </div>
  );
}
