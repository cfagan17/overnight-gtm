-- Supabase test shim
--
-- Recreates the small part of a Supabase project that the Atomic CRM schema and
-- the Overnight migrations depend on, so the whole stack can be tested on a
-- plain Postgres 16. On a real Supabase project, do NOT run this file: every object
-- here already exists there.
--
-- Mirrors Supabase behaviour:
--   * roles anon, authenticated, service_role (service_role bypasses RLS)
--   * auth.uid() / auth.jwt() read the request.jwt.claims setting, as PostgREST sets it
--   * extensions, storage and net schemas with the objects Atomic references

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end $$;

-- Supabase grants every new table, sequence and function in public to the API roles by
-- default (row-level security is what then protects rows). Mirror that here, so the tests see
-- the same grants a real project does.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;

create schema if not exists extensions;
create schema if not exists auth;
create schema if not exists storage;
create schema if not exists net;

create extension if not exists citext with schema extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists unaccent with schema extensions;

-- The "http" extension is not available on plain Postgres. Atomic only calls it from
-- plpgsql (favicon lookup), so a stub with the same signature is enough for tests.
create or replace function extensions.http_get(url text)
returns table (status int, content text) language sql as $$ select 0, ''::text $$;

create or replace function net.http_post(url text, body jsonb default '{}'::jsonb,
  params jsonb default '{}'::jsonb, headers jsonb default '{}'::jsonb, timeout_milliseconds int default 1000)
returns bigint language sql as $$ select 0::bigint $$;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb default '{}'::jsonb,
  raw_app_meta_data jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  banned_until timestamptz,
  is_sso_user boolean default false,
  email_confirmed_at timestamptz
);

create or replace function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;

create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(auth.jwt() ->> 'sub', '')::uuid
$$;

create or replace function auth.role() returns text language sql stable as $$
  select auth.jwt() ->> 'role'
$$;

create table if not exists storage.buckets (id text primary key, name text, public boolean default false);
create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets(id),
  name text,
  owner uuid,
  metadata jsonb
);
alter table storage.objects enable row level security;

grant usage on schema public, extensions, auth, storage to anon, authenticated, service_role;
grant execute on all functions in schema auth to anon, authenticated, service_role;
