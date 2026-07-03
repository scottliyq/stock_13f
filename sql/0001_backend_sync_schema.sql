create extension if not exists pgcrypto;

create table if not exists public.raw_8k_filings (
    accession_number text primary key,
    ticker text,
    form text not null,
    filing_date date,
    company_name text,
    payload jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.raw_13dg_filings (
    accession_number text primary key,
    ticker text,
    form text not null,
    filing_date date,
    company_name text,
    payload jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.raw_13f_sync_runs (
    run_key text primary key,
    latest_report_date date,
    quarters integer not null,
    top_limit integer not null,
    output_paths jsonb not null default '[]'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.mart_13f_quarterly_movers (
    row_key text primary key,
    report_date date not null,
    security_type text not null,
    ranking_type text not null,
    rank integer not null,
    issuer text not null,
    cusip text not null,
    ticker text,
    business_summary text,
    new_manager_count integer not null default 0,
    new_entry_total_value_usd bigint not null default 0,
    reduced_manager_count integer not null default 0,
    reduced_total_value_usd bigint not null default 0,
    holder_manager_count integer not null default 0,
    total_holding_value_usd bigint not null default 0
);

create index if not exists idx_mart_13f_quarterly_movers_period
    on public.mart_13f_quarterly_movers (report_date, security_type, ranking_type, rank);

create index if not exists idx_mart_13f_quarterly_movers_ticker
    on public.mart_13f_quarterly_movers (ticker, report_date);

create table if not exists public.dim_manager_watchlist (
    manager_cik bigint primary key,
    manager_name text not null,
    focus_areas text not null,
    short_description text not null,
    display_order integer not null,
    is_active boolean not null default true
);

create table if not exists public.mart_manager_profile (
    manager_cik bigint primary key references public.dim_manager_watchlist (manager_cik) on delete cascade,
    manager_name text not null,
    focus_areas text not null,
    short_description text not null,
    display_order integer not null,
    is_active boolean not null default true
);

create table if not exists public.mart_manager_research_snapshot (
    snapshot_key text primary key,
    manager_count integer not null default 0,
    latest_report_period date,
    available_report_periods jsonb not null default '[]'::jsonb
);
