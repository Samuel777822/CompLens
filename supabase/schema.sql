-- CompLens database. Run this once in the Supabase SQL editor (safe to run again).
-- It keeps only the LAST 10 scans: when the 11th arrives, the oldest one is removed.

create table if not exists public.scans (
  id                 uuid primary key default gen_random_uuid(),
  created_at         timestamptz not null default now(),
  input_mode         text not null check (input_mode in ('image', 'text')),
  category           text not null,
  pack_type          text,
  image_path         text,                 -- file name inside the label-images bucket
  raw_text           text,
  avg_ocr_confidence real,
  verdict            text not null check (verdict in ('COMPLIANT','NON_COMPLIANT','NEEDS_REVIEW','EXEMPT')),
  fail_count         int  not null default 0,
  review_count       int  not null default 0,
  result             jsonb not null        -- full ScanResult (every field + rule_reference)
);

create index if not exists scans_created_at_idx on public.scans (created_at desc);

-- The backend uses the service-role key (bypasses RLS). With RLS on and no policies,
-- nobody else (anon / authenticated keys) can read or write this table.
alter table public.scans enable row level security;

-- Keep the newest 10 rows. The app also deletes the old photo from storage before it inserts;
-- this trigger is the backstop so the table can never grow past 10, whatever writes to it.
create or replace function public.keep_last_10_scans() returns trigger
language plpgsql set search_path = public as $$
begin
  delete from public.scans
  where id in (select id from public.scans order by created_at desc, id desc offset 10);
  return null;
end $$;

drop trigger if exists scans_keep_last_10 on public.scans;
create trigger scans_keep_last_10
  after insert on public.scans
  for each statement execute function public.keep_last_10_scans();

-- Private bucket for uploaded label photos (the app removes a photo together with its scan).
insert into storage.buckets (id, name, public)
values ('label-images', 'label-images', false)
on conflict (id) do nothing;
