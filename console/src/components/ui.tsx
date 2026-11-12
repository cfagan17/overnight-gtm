import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { LEVELS, LOOP, loopName, ACTION_LABEL } from '../lib/meta';
import { initials } from '../lib/format';

export function Page({ title, kicker, actions, children }: { title: ReactNode; kicker?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-8 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          {kicker && <div className="label mb-2">{kicker}</div>}
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function Card({ children, className = '', title, right, pad = true }: { children: ReactNode; className?: string; title?: ReactNode; right?: ReactNode; pad?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b border-night-600/60 px-5 py-3.5">
          <h2 className="text-sm font-bold">{title}</h2>
          {right}
        </div>
      )}
      <div className={pad ? 'p-5' : ''}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, color }: { label: string; value: ReactNode; sub?: ReactNode; color?: string }) {
  return (
    <div className="card p-5">
      <div className="label">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="mt-1 text-sm text-ink-muted">{sub}</div>}
    </div>
  );
}

export function Badge({ children, color = '#52525b', solid = false, className = '' }: { children: ReactNode; color?: string; solid?: boolean; className?: string }) {
  if (solid) return <span className={`inline-flex items-center whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium text-white ${className}`} style={{ background: color }}>{children}</span>;
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border border-night-600 bg-night-800 px-1.5 py-0.5 text-xs font-medium text-ink ${className}`}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />{children}
    </span>
  );
}

export const LoopBadge = ({ loop }: { loop: string }) => <Badge color={LOOP[loop]?.color || '#b45309'}>{loopName(loop)}</Badge>;
export const ActionBadge = ({ action }: { action: string }) => <Badge color="#52525b">{ACTION_LABEL[action] || action}</Badge>;

export function Strength({ s }: { s: string }) {
  return s === 'strong' ? <Badge color="#047857">strong</Badge> : <Badge color="#71717a">weak</Badge>;
}

export function Outcome({ o }: { o: string | null }) {
  if (!o) return <Badge color="#b45309">waiting</Badge>;
  const c = o === 'accepted' ? '#047857' : o === 'edited' ? '#b45309' : '#b91c1c';
  return <Badge color={c}>{o}</Badge>;
}

export function Avatar({ name, color = '#1d4ed8', size = 32 }: { name: string; color?: string; size?: number }) {
  return (
    <div className="grid shrink-0 place-items-center rounded-full font-bold text-night-950"
      style={{ width: size, height: size, background: color, fontSize: size * 0.38 }}>{initials(name)}</div>
  );
}

export function Ladder({ level, max, size = 'md' }: { level: number; max: number; size?: 'sm' | 'md' }) {
  const w = size === 'sm' ? 'h-1.5 w-5' : 'h-2 w-8';
  return (
    <div className="flex items-center gap-1" title={`Level ${level}: ${LEVELS[level]}. Cap: level ${max}.`}>
      {LEVELS.map((_, i) => (
        <div key={i} className={`${w} rounded-full ${i <= level ? 'bg-loop' : i <= max ? 'bg-night-600' : 'bg-night-800 ring-1 ring-night-600'}`} />
      ))}
    </div>
  );
}

export function Bar({ parts }: { parts: { v: number; c: string; label?: string }[] }) {
  const total = parts.reduce((a, p) => a + p.v, 0) || 1;
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-night-700">
      {parts.map((p, i) => <div key={i} title={p.label} style={{ width: `${(p.v / total) * 100}%`, background: p.c }} />)}
    </div>
  );
}

export function Spinner() {
  return <div className="flex items-center gap-3 p-6 text-sm text-ink-muted"><div className="h-4 w-4 animate-spin rounded-full border-2 border-prim border-t-transparent" />Loading</div>;
}
export function Err({ e }: { e: string }) {
  return <div className="rounded-md border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-700">{e}</div>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-night-600 p-8 text-center text-sm text-ink-muted">{children}</div>;
}

export function SubjectLink({ type, id, name }: { type: string; id: string; name?: string }) {
  if (type === 'company') return <Link className="font-semibold text-ink hover:text-prim" to={`/accounts/${id}`}>{name || `Account ${id}`}</Link>;
  if (type === 'loop') return <Link className="font-semibold text-ink hover:text-prim" to={`/loops/${id}`}>{name || loopName(id)}</Link>;
  return <span className="font-semibold">{name || `${type} ${id}`}</span>;
}

// Toasts
let push: (m: { text: string; kind?: 'ok' | 'err' }) => void = () => {};
export const toast = (text: string, kind: 'ok' | 'err' = 'ok') => push({ text, kind });
export function Toasts() {
  const [items, setItems] = useState<{ id: number; text: string; kind?: string }[]>([]);
  useEffect(() => { push = (m) => { const id = Date.now() + Math.random(); setItems((x) => [...x, { id, ...m }]); setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4200); }; }, []);
  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex flex-col gap-2">
      {items.map((i) => (
        <div key={i.id} className={`card pointer-events-auto max-w-sm px-4 py-3 text-sm shadow-lg ${i.kind === 'err' ? 'border-red-400/40 text-red-700' : 'border-control/40'}`}>{i.text}</div>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: ReactNode }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto rounded-md border border-night-600 bg-night-850 p-1">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`whitespace-nowrap rounded px-3.5 py-1.5 text-sm font-semibold transition ${value === t.id ? 'bg-night-700 text-ink' : 'text-ink-muted hover:text-ink'}`}>{t.label}</button>
      ))}
    </div>
  );
}
