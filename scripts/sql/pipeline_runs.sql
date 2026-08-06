-- Refresh-run history, and the lease that keeps two runs from overlapping.
-- Run once in the Supabase SQL editor, after scripts/sql/content_pipeline.sql.
--
-- The pipeline has three triggers now: the nightly Vercel cron, the button in /admin/scraping,
-- and the local CLI. Before this table the only record of a run was its HTTP status code in
-- Vercel's log -- which cannot say what changed, only that something did or did not fail. A
-- reviewer opening the admin page had no way to know whether last night's run found anything.
--
-- One row per run, holding the same report the endpoint returns. That makes the admin card's
-- "last run" line true of cron runs as well as of button presses.


create table if not exists public.pipeline_runs (
    id           bigint generated always as identity primary key,
    trigger      text not null check (trigger in ('cron', 'admin', 'cli')),
    dry_run      boolean not null default false,
    forced       boolean not null default false,

    started_at   timestamptz not null default now(),
    finished_at  timestamptz,               -- null = in flight; see the index below

    ok           boolean,
    changed      boolean,                   -- did any sink actually write something
    report       jsonb,                     -- the per-sink payload, as the API returns it

    constraint pipeline_runs_finished_after_start
        check (finished_at is null or finished_at >= started_at)
);


-- THE LEASE. At most one run in flight across the whole table, enforced by the database.
--
-- The alternative -- read "is anything running?", then insert -- is racy exactly when it
-- matters: the cron fires at 06:17 UTC whether or not someone is holding the button down, and
-- two runs that both pass the read would both upload the same new tool to the vector store.
-- The second upsert would then overwrite the first one's row, leaving an orphaned file in the
-- store with nothing pointing at it -- and on this API a file cannot be read back or detached
-- without being destroyed, so that is not a mistake automation can clean up.
--
-- Indexing on the constant `(true)` makes the uniqueness table-wide rather than per-value: any
-- second row with a null finished_at violates it, and the caller gets a 23505 to turn into a
-- 409. A run whose function timed out leaves its row open forever, so callers close anything
-- older than a fixed window before claiming -- see sweep_stale_runs() in
-- scripts/content_pipeline/state.py.
create unique index if not exists pipeline_runs_one_in_flight
    on public.pipeline_runs ((true)) where finished_at is null;


-- Reading history is always "the newest few", never a scan.
create index if not exists pipeline_runs_started_idx
    on public.pipeline_runs (started_at desc);


-- Same posture as the other pipeline tables: the API reaches Supabase with the service key
-- from the server only, so RLS on with no policy denies anon/authenticated outright while the
-- service role keeps working.
alter table public.pipeline_runs enable row level security;
