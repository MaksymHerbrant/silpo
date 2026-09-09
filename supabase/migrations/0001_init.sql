-- Нутрі-Кошик — початкова схема
-- Постгрес (Supabase). Supabase Auth НЕ використовується: авторизація через Telegram initData.
-- Доступ до всіх таблиць — тільки з бекенду через service_role key.

create extension if not exists "pgcrypto";

-- 1. Користувачі -------------------------------------------------------------
create table if not exists public.users (
    id          uuid primary key default gen_random_uuid(),
    telegram_id bigint      not null unique,
    username    text,
    first_name  text,
    language_code text,
    created_at  timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

-- 2. OAuth-токени Сільпо -----------------------------------------------------
-- access_token / refresh_token зберігаються у ЗАШИФРОВАНОМУ вигляді
-- (Fernet, ключ TOKEN_ENCRYPTION_KEY живе тільки в env бекенду).
-- У фронтенд ці значення не потрапляють ніколи.
create table if not exists public.silpo_oauth_tokens (
    user_id       uuid primary key references public.users(id) on delete cascade,
    access_token  text        not null,   -- ciphertext
    refresh_token text,                   -- ciphertext
    token_type    text        not null default 'Bearer',
    scope         text,
    expires_at    timestamptz not null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- Тимчасове сховище PKCE-стану між /auth/silpo/start і /auth/silpo/callback
create table if not exists public.silpo_oauth_states (
    state          text primary key,
    user_id        uuid not null references public.users(id) on delete cascade,
    code_verifier  text not null,
    redirect_uri   text not null,
    created_at     timestamptz not null default now(),
    expires_at     timestamptz not null default (now() + interval '10 minutes'),
    consumed_at    timestamptz
);
create index if not exists silpo_oauth_states_user_idx on public.silpo_oauth_states(user_id);

-- Одноразовий токен для повернення в Mini App через startapp=<token>
create table if not exists public.startapp_tokens (
    token       text primary key,
    user_id     uuid not null references public.users(id) on delete cascade,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null default (now() + interval '15 minutes'),
    consumed_at timestamptz
);

-- 3. Тижневі зрізи -----------------------------------------------------------
create table if not exists public.weekly_snapshots (
    id                uuid primary key default gen_random_uuid(),
    user_id           uuid not null references public.users(id) on delete cascade,
    week_start_date   date not null,
    avg_calories      numeric(10,2),
    avg_protein       numeric(10,2),
    avg_fat           numeric(10,2),
    avg_carbs         numeric(10,2),
    total_added_sugar numeric(10,2),
    health_score      integer check (health_score between 0 and 100),
    source            text not null default 'orders',  -- orders | cart
    created_at        timestamptz not null default now(),
    unique (user_id, week_start_date)
);
create index if not exists weekly_snapshots_user_week_idx
    on public.weekly_snapshots(user_id, week_start_date desc);

-- 4. Кеш аналізу кошика ------------------------------------------------------
create table if not exists public.cart_analysis_cache (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references public.users(id) on delete cascade,
    cart_id      text not null,
    computed_at  timestamptz not null default now(),
    items_json   jsonb not null,
    health_score integer,
    unique (user_id, cart_id)
);
create index if not exists cart_analysis_cache_user_idx
    on public.cart_analysis_cache(user_id, computed_at desc);

-- 5. Пропозиції заміни -------------------------------------------------------
create table if not exists public.swap_suggestions (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null references public.users(id) on delete cascade,
    cart_id              text,
    original_product_id  text not null,
    original_title       text,
    suggested_product_id text not null,
    suggested_title      text,
    reason               text,
    score_delta          numeric(6,2),
    is_own_brand         boolean not null default false,
    accepted             boolean,          -- null = ще не вирішено; метрика "% прийнятих свопів"
    created_at           timestamptz not null default now(),
    decided_at           timestamptz
);
create index if not exists swap_suggestions_user_idx
    on public.swap_suggestions(user_id, created_at desc);

-- 6. Лог JSON-RPC викликів MCP (для /debug/mcp-log і демо журі) ---------------
create table if not exists public.mcp_call_log (
    id          bigserial primary key,
    user_id     uuid references public.users(id) on delete cascade,
    session_id  text,
    tool_name   text not null,
    request     jsonb,
    response    jsonb,
    status      text not null,      -- ok | error
    http_status integer,
    duration_ms integer,
    created_at  timestamptz not null default now()
);
create index if not exists mcp_call_log_user_idx on public.mcp_call_log(user_id, id desc);

-- RLS: доступ лише service_role (anon/authenticated не мають політик => заборонено).
alter table public.users                enable row level security;
alter table public.silpo_oauth_tokens   enable row level security;
alter table public.silpo_oauth_states   enable row level security;
alter table public.startapp_tokens      enable row level security;
alter table public.weekly_snapshots     enable row level security;
alter table public.cart_analysis_cache  enable row level security;
alter table public.swap_suggestions     enable row level security;
alter table public.mcp_call_log         enable row level security;
