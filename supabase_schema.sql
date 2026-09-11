-- Chạy một lần trong Supabase: SQL Editor > New query > Run
create table if not exists public.scripts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    name text not null check (char_length(name) between 1 and 120),
    payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    unique (user_id, name)
);

alter table public.scripts enable row level security;

create policy "Users read own scripts" on public.scripts
for select to authenticated using (auth.uid() = user_id);

create policy "Users create own scripts" on public.scripts
for insert to authenticated with check (auth.uid() = user_id);

create policy "Users update own scripts" on public.scripts
for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "Users delete own scripts" on public.scripts
for delete to authenticated using (auth.uid() = user_id);
