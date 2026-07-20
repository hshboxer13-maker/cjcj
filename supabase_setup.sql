-- Supabase SQL Editor(https://supabase.com/dashboard/project/xfmpdbzwtslwvwoqoypc/sql/new)에서
-- 이 파일 전체를 붙여넣고 Run 하세요.

create table if not exists public.scm_dashboard_snapshots (
  id uuid primary key default gen_random_uuid(),
  payload jsonb not null,
  created_at timestamptz not null default now()
);

-- 최신 스냅샷을 빠르게 조회하기 위한 인덱스
create index if not exists scm_dashboard_snapshots_created_at_idx
  on public.scm_dashboard_snapshots (created_at desc);

alter table public.scm_dashboard_snapshots enable row level security;

-- publishable(anon) 키는 읽기만 허용 (누구나 대시보드는 볼 수 있어야 하므로)
create policy "anyone can read snapshots"
  on public.scm_dashboard_snapshots
  for select
  to anon
  using (true);

-- insert/update/delete 정책은 의도적으로 만들지 않음
-- -> anon(publishable) 키로는 쓰기가 항상 거부됨
-- -> 업로드는 service_role 키를 쓰는 upload_to_supabase.py 로컬 스크립트로만 수행 (RLS 우회)
