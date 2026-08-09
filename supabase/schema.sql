-- Árfigyelő – Supabase séma
-- Futtatás: Supabase Dashboard → SQL Editor → paste → Run
--
-- Három tábla:
--   products        – a figyelt termékek katalógusa (kézzel/seeddel töltve)
--   price_snapshots – napi árpillanatképek, ez az idősor
--   ai_verdicts     – Claude által generált trend-összefoglalók, cache-elve

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
create table if not exists public.products (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,         -- URL-barát azonosító, pl. sony-wh-1000xm6-fekete
  name        text not null,
  brand       text,
  category    text not null default 'fejhallgato',
  url         text not null,                -- a scrapelt termékoldal
  image_url   text,
  shop        text not null default 'alza.hu',
  currency    text not null default 'HUF',
  active      boolean not null default true, -- false = már nem scrapeljük, de a history megmarad
  created_at  timestamptz not null default now()
);

comment on table public.products is 'Figyelt termékek. Egy shop, egy kategória, 10-15 sor.';

-- ---------------------------------------------------------------------------
-- price_snapshots
-- ---------------------------------------------------------------------------
create table if not exists public.price_snapshots (
  id            bigserial primary key,
  product_id    uuid not null references public.products(id) on delete cascade,
  price         integer,                     -- fillér nélkül, HUF egész; NULL = nem volt kiolvasható ár
  list_price    integer,                     -- áthúzott / eredeti ár, ha van akció
  availability  text,                        -- 'InStock' | 'OutOfStock' | 'PreOrder' | ...
  captured_on   date not null default (now() at time zone 'Europe/Budapest')::date,
  captured_at   timestamptz not null default now(),
  source        text not null default 'jsonld', -- 'jsonld' | 'dom' – melyik extractor adta
  -- Napi 1 mérés: ugyanarra a termékre / napra csak egy sor legyen.
  -- Újrafuttatás felülírja (upsert), nem duplikál.
  unique (product_id, captured_on)
);

create index if not exists price_snapshots_product_date_idx
  on public.price_snapshots (product_id, captured_on desc);

comment on table public.price_snapshots is 'Napi árpillanatképek. (product_id, captured_on) egyedi -> az upsert idempotens.';

-- ---------------------------------------------------------------------------
-- ai_verdicts
-- ---------------------------------------------------------------------------
-- A Claude-hívás drága és lassú, ezért cache-eljük. A cache kulcsa a termék +
-- az ártörténet ujjlenyomata: ha nem változott az idősor, nem hívunk újra.
create table if not exists public.ai_verdicts (
  id            bigserial primary key,
  product_id    uuid not null references public.products(id) on delete cascade,
  history_hash  text not null,               -- sha256 a felhasznált idősorból
  trend         text not null check (trend in ('csokkeno', 'emelkedo', 'stabil')),
  headline      text not null,               -- rövid címke, pl. "Most jó vétel"
  verdict       text not null,               -- 1-2 mondatos, emberi nyelvű összefoglaló
  model         text not null,
  created_at    timestamptz not null default now(),
  unique (product_id, history_hash)
);

create index if not exists ai_verdicts_product_idx
  on public.ai_verdicts (product_id, created_at desc);

comment on table public.ai_verdicts is 'Claude-generált trend-verdiktek, az ártörténet hash-ére cache-elve.';

-- ---------------------------------------------------------------------------
-- Kényelmi nézet: minden termék legfrissebb ára + 30 napos min/max
-- ---------------------------------------------------------------------------
create or replace view public.product_price_summary as
select
  p.id,
  p.slug,
  p.name,
  p.brand,
  p.url,
  p.image_url,
  p.currency,
  latest.price          as current_price,
  latest.list_price     as current_list_price,
  latest.availability   as availability,
  latest.captured_on    as last_checked_on,
  stats.min_30d,
  stats.max_30d,
  stats.avg_30d,
  stats.sample_count_30d
from public.products p
left join lateral (
  select price, list_price, availability, captured_on
  from public.price_snapshots s
  where s.product_id = p.id and s.price is not null
  order by s.captured_on desc
  limit 1
) latest on true
left join lateral (
  select
    min(price)                    as min_30d,
    max(price)                    as max_30d,
    round(avg(price))::integer    as avg_30d,
    count(*)                      as sample_count_30d
  from public.price_snapshots s
  where s.product_id = p.id
    and s.price is not null
    and s.captured_on >= current_date - interval '30 days'
) stats on true
where p.active;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- A dashboard publikus és csak olvas -> anon kulccsal SELECT szabad.
-- Írni kizárólag a scraper tud, service_role kulccsal (az RLS-t megkerüli).
alter table public.products       enable row level security;
alter table public.price_snapshots enable row level security;
alter table public.ai_verdicts    enable row level security;

drop policy if exists "public read products" on public.products;
create policy "public read products"
  on public.products for select to anon, authenticated using (true);

drop policy if exists "public read snapshots" on public.price_snapshots;
create policy "public read snapshots"
  on public.price_snapshots for select to anon, authenticated using (true);

drop policy if exists "public read verdicts" on public.ai_verdicts;
create policy "public read verdicts"
  on public.ai_verdicts for select to anon, authenticated using (true);
