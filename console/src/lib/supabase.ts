import { createClient } from '@supabase/supabase-js';

// The demo project. Point VITE_SUPABASE_URL and VITE_SUPABASE_KEY at your own project to use
// the console with your data. The key is a publishable key: everything a person sees or does
// is decided by row-level security and the database functions, never by this app.
const url = import.meta.env.VITE_SUPABASE_URL || 'https://migmmndgaqbygymoklot.supabase.co';
const key = import.meta.env.VITE_SUPABASE_KEY || 'sb_publishable_1erAYlvNeenzMbik-5fIGg_ScqCVg-N';

export const supabase = createClient(url, key, { auth: { persistSession: true, storageKey: 'overnight-console' } });
export const DEMO = !import.meta.env.VITE_SUPABASE_URL;
export const DEMO_PASSWORD = 'overnight-demo';

export function errText(e: any): string {
  const m = e?.message || String(e);
  return m.replace(/^ea:\s*/, '');
}
