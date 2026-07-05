create table if not exists public.mart_manager_security_latest (
    row_key text primary key,
    report_date date not null,
    previous_report_date date not null,
    manager_cik bigint not null,
    manager_name text not null,
    ticker text,
    issuer text not null,
    cusip text not null,
    status text not null,
    previous_value_usd bigint not null default 0,
    current_value_usd bigint not null default 0,
    value_change_usd bigint not null default 0,
    found_in_current boolean not null default false,
    found_in_previous boolean not null default false
);

create index if not exists idx_mart_manager_security_latest_lookup
    on public.mart_manager_security_latest (report_date, manager_cik, ticker, cusip);
