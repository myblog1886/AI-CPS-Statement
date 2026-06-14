-- Run this in Supabase SQL editor before deploying

create table if not exists payroll_runs (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  establishment_id text,
  month int not null,
  year int not null,
  total_employees int,
  total_gross numeric,
  total_net numeric,
  total_pf_challan numeric,
  total_esic_challan numeric,
  results_json jsonb,
  ecr_text text,
  esic_csv text,
  created_at timestamptz default now()
);

create table if not exists compare_sessions (
  id uuid primary key default gen_random_uuid(),
  label text,
  run_ids uuid[],
  newboss_json jsonb,
  created_at timestamptz default now()
);
