import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase, DEMO_PASSWORD } from './supabase';

export type Me = { userId: string; email: string; name: string; role: string; salesId: number | null };
type Ctx = { session: Session | null; me: Me | null; loading: boolean; signInAs: (email: string, password?: string) => Promise<string | null>; signOut: () => Promise<void> };
const SessionCtx = createContext<Ctx>(null as any);

async function loadMe(s: Session): Promise<Me> {
  const uid = s.user.id;
  const [{ data: sales }, { data: pr }] = await Promise.all([
    supabase.from('sales').select('id, first_name, last_name, email').eq('user_id', uid).maybeSingle(),
    supabase.from('principals').select('role').eq('user_id', uid).maybeSingle(),
  ]);
  return {
    userId: uid, email: s.user.email || '', salesId: sales?.id ?? null,
    name: sales ? `${sales.first_name} ${sales.last_name}` : s.user.email || 'Signed in',
    role: pr?.role || 'rep',
  };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      setSession(data.session);
      if (data.session) setMe(await loadMe(data.session));
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange(async (_e, s) => {
      setSession(s);
      setMe(s ? await loadMe(s) : null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);
  const signInAs = async (email: string, password = DEMO_PASSWORD) => {
    setLoading(true);
    await supabase.auth.signOut();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    return error ? error.message : null;
  };
  const signOut = async () => { await supabase.auth.signOut(); };
  return <SessionCtx.Provider value={{ session, me, loading, signInAs, signOut }}>{children}</SessionCtx.Provider>;
}
export const useSession = () => useContext(SessionCtx);
