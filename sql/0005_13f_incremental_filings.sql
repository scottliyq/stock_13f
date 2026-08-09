create table if not exists public.raw_13f_filings (
    accession_number text primary key,
    manager_cik bigint not null,
    manager_name text not null,
    form text not null,
    filing_date date not null,
    report_date date not null,
    filing_url text,
    payload jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_raw_13f_filings_report_date
    on public.raw_13f_filings (report_date, filing_date desc);

create index if not exists idx_raw_13f_filings_manager
    on public.raw_13f_filings (report_date, manager_cik, filing_date desc);
