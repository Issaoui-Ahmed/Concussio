-- Content pipeline state. Run once in the Supabase SQL editor.
--
-- Supabase is the "what we have" side of every comparison the pipeline makes. A Vercel
-- function cannot write files, so a committed file can never be the record of what was last
-- published -- see api/cron.py. These three tables replace three file-based records that all
-- drifted from reality:
--
--     all_rec_markdown.md        -> content_state       (never updated on Vercel; drifted)
--     (nothing)                  -> vector_store_files  (the store was synced by hand)
--     data/resource-pairs.json   -> resource_pairs      (rebuilt only by a local CLI run)
--
-- Each table is read, compared against a fresh scrape, and written back only when the scrape
-- differs. Nothing here is a cache: these rows are the authority.


-- 1. ------------------------------------------------------------------------------------
-- What we last published, per sink. Today that is the recommendations corpus.
--
-- The full markdown is stored, not just its hash, for two reasons: the hash alone cannot tell
-- you *what* changed between two runs, and this row is now the only durable copy of what the
-- copilots were actually given (the committed .md file is a local-dev artefact that no
-- deployment writes to).
create table if not exists public.content_state (
    sink          text primary key,          -- 'corpus'
    content       text not null,
    content_hash  text not null,
    published_at  timestamptz not null default now(),
    meta          jsonb,                     -- domain/recommendation counts from the run
    updated_at    timestamptz not null default now()
);


-- 2. ------------------------------------------------------------------------------------
-- The Living Guideline Tools link set, and the Fuel IX file each link owns.
--
-- This table does two jobs deliberately. It is the stored link set the scrape is compared
-- against (one row per link), AND the record of which vector-store file belongs to which link.
-- Keeping them together means "which links do we have?" and "what may automation touch?" can
-- never disagree.
--
-- OWNERSHIP IS THE SAFETY PROPERTY. The combined store holds 38 files: 28 living-guideline
-- tools and 10 research papers that were curated by hand and have no upstream link. The
-- pipeline may only ever detach a file it has a row for. A paper, or the IPV supplement, has
-- no row and is therefore invisible to automation -- not by a filename convention that could
-- be broken by a rename, but because the mapping simply does not exist.
--
-- Change detection is on the LINK, never on file content. The adopted files are hand-made .txt
-- extractions of pages that serve HTML, so comparing downloaded bytes against them would report
-- "changed" on every run forever.
create table if not exists public.vector_store_files (
    source_url    text primary key,          -- the living-guideline-tool link, normalized
    title         text,                      -- anchor text at adoption/upload time, for humans
    store_id      text not null,             -- Fuel IX vector store holding the file
    file_id       text not null,             -- Fuel IX file id
    filename      text,

    -- 'adopted'  uploaded by a human before the pipeline existed -- a hand conversion of a tool
    --            into clean .txt. NEVER removed automatically. Removal is permanent on this
    --            API (deleting a store attachment destroys the file, and GET /files/{id}/content
    --            is a 404, so it can be neither kept nor archived), and these exist nowhere
    --            else -- not in git, not on the site in that form. A vanished link is reported
    --            for a person to action instead.
    -- 'pipeline' fetched and uploaded by a refresh run. Re-fetchable from source_url, so a
    --            wrong removal costs a download; safe to retire automatically.
    uploaded_by   text not null default 'pipeline' check (uploaded_by in ('adopted', 'pipeline')),

    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists vector_store_files_store_idx
    on public.vector_store_files (store_id);


-- 3. ------------------------------------------------------------------------------------
-- The EN->FR pairing table. Supersedes resource_overrides and data/resource-pairs.json.
--
-- One row per English tool, so "which French document does this resolve to?" is a primary-key
-- lookup rather than a precedence puzzle across three stores. `origin` decides who may write:
--
--     'auto'    the tool-number matcher derived it. A refresh run may overwrite or retire it.
--     'manual'  a person decided it in /admin/scraping. A refresh run must never touch it.
--
-- A null fr_url is a suppression: "this English tool has no French counterpart", which the
-- matcher must not keep re-proposing. That replaces the old kind='unpair' row.
create table if not exists public.resource_pairs (
    en_url        text primary key,
    fr_url        text,                      -- null = suppressed, no French counterpart
    fr_title      text,
    origin        text not null check (origin in ('auto', 'manual')),
    source        text,                      -- 'tool-number' for derived pairs
    note          text,
    created_by    text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists resource_pairs_origin_idx
    on public.resource_pairs (origin);


-- Migration ------------------------------------------------------------------------------
-- Carry the existing manual decisions across. Everything in resource_overrides was made by a
-- person in the admin UI, so it all lands as origin='manual' and becomes immune to the
-- refresh job -- which is exactly the protection it had before.
--
-- kind='unpair' becomes a row with a null fr_url, preserving the suppression.
insert into public.resource_pairs (en_url, fr_url, fr_title, origin, source, note, created_by, created_at)
select
    o.en_url,
    case when o.kind = 'pair' then o.fr_url else null end,
    o.fr_title,
    'manual',
    'migrated-from-resource_overrides',
    o.note,
    o.created_by,
    o.created_at
from public.resource_overrides o
where o.kind in ('pair', 'unpair')
on conflict (en_url) do nothing;


-- The API reaches Supabase with the service key from the server only; no browser talks to
-- these tables directly. RLS on with no policy denies anon/authenticated outright while the
-- service role (which bypasses RLS) keeps working.
alter table public.content_state       enable row level security;
alter table public.vector_store_files  enable row level security;
alter table public.resource_pairs      enable row level security;


-- resource_overrides is intentionally left in place after this runs. Drop it only once the new
-- table has been serving for a while:
--     drop table public.resource_overrides;
