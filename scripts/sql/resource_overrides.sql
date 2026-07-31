-- Manual EN->FR pairing decisions made from /admin/scraping.
--
-- Run once in the Supabase SQL editor. Everything the admin UI writes lands here; the
-- reviewed file data/resource-pairs.json stays the committed baseline and is never mutated at
-- runtime (a Vercel function cannot write files -- see api/cron.py).
--
-- Deleting every row in this table returns the app to exactly what the committed baseline plus
-- the matcher produce. That is what the UI's "Clear manual overrides" button does, and it is
-- why nothing here is destructive: the baseline is always recoverable.

create table if not exists public.resource_overrides (
    id          uuid primary key default gen_random_uuid(),

    -- 'pair'   an approved EN->FR mapping.
    -- 'unpair' a suppression: this English resource has no French counterpart, whatever the
    --          committed baseline or the matcher would otherwise say. It exists because the
    --          baseline is a file, and a Vercel function cannot edit a file at runtime — so
    --          removing a baseline link has to be recorded as a row instead.
    kind        text not null check (kind in ('pair', 'unpair')),

    en_url      text not null,
    fr_url      text,
    fr_title    text,
    note        text,

    created_at  timestamptz not null default now(),
    created_by  text
);

-- Keyed on en_url alone, mirroring the pipeline's own index (PairSet.pair_index() maps a
-- normalized en_url to one Pair). Re-pairing an English resource replaces its previous mapping
-- rather than creating an ambiguous second one.
create unique index if not exists resource_overrides_pair_en_key
    on public.resource_overrides (en_url)
    where kind = 'pair';

-- Same reasoning for suppressions: one per English resource, so "is this suppressed?" is a set
-- membership test rather than a count.
create unique index if not exists resource_overrides_unpair_en_key
    on public.resource_overrides (en_url)
    where kind = 'unpair';

-- The API reaches Supabase with the service key from the server only; no browser ever talks to
-- this table directly. RLS on with no policy therefore denies anon/authenticated outright while
-- leaving the service role (which bypasses RLS) working.
alter table public.resource_overrides enable row level security;
