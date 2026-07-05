create table if not exists public.raw_13dg_reporting_persons (
    row_key text primary key,
    accession_number text not null references public.raw_13dg_filings (accession_number) on delete cascade,
    person_index integer not null,
    reporting_person_name text not null default '',
    reporting_person_cik text not null default '',
    reporting_person_type text not null default '',
    aggregate_amount bigint,
    percent_of_class double precision,
    sole_voting_power bigint,
    shared_voting_power bigint,
    sole_dispositive_power bigint,
    shared_dispositive_power bigint,
    synced_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_raw_13dg_reporting_persons_accession
    on public.raw_13dg_reporting_persons (accession_number, person_index);

create index if not exists idx_raw_13dg_reporting_persons_manager
    on public.raw_13dg_reporting_persons (reporting_person_cik, reporting_person_name);

create table if not exists public.raw_13dg_sync_sources (
    row_key text primary key,
    accession_number text not null references public.raw_13dg_filings (accession_number) on delete cascade,
    sync_mode text not null,
    source_key text not null,
    synced_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_raw_13dg_sync_sources_accession
    on public.raw_13dg_sync_sources (accession_number);

create index if not exists idx_raw_13dg_sync_sources_mode
    on public.raw_13dg_sync_sources (sync_mode, source_key);
