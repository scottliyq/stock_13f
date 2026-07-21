create table if not exists public.sync_checkpoints (
    job_name text primary key,
    status text not null,
    started_at timestamptz not null,
    finished_at timestamptz not null,
    rows_written bigint not null default 0,
    checkpoints_updated integer not null default 0,
    warnings jsonb not null default '[]'::jsonb,
    error_summary text not null default '',
    details jsonb not null default '{}'::jsonb,
    cursor jsonb not null default '{}'::jsonb
);

create index if not exists idx_sync_checkpoints_finished_at
    on public.sync_checkpoints (finished_at desc);

grant select on public.sync_checkpoints to anon, authenticated;
