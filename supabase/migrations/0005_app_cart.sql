-- Централізований кошик застосунку.
--
-- Ключове рішення: товар, доданий з БУДЬ-ЯКОГО екрана, потрапляє сюди, а не
-- одразу в кошик Сільпо. Запис у MCP лишається один — на кнопку «Оформити».
-- Так гість може збирати набір по кількох екранах і передумати без наслідків.
create table if not exists public.app_cart (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references public.users(id) on delete cascade,
    product_id  text not null,
    slug        text,
    name        text,
    image       text,
    price       numeric(10,2),
    quantity    integer not null default 1,
    -- З якого екрана додали: nutrition | promo | analytics | plan
    source      text,
    added_at    timestamptz not null default now(),
    unique (user_id, product_id)
);
create index if not exists app_cart_user_idx on public.app_cart(user_id, added_at desc);
alter table public.app_cart enable row level security;

-- Позначка проходження онбордингу.
-- Без неї не відрізнити «гість обрав автопілот» від «гість ще не бачив питання»:
-- mode має NOT NULL DEFAULT, тому сам по собі нічого не каже.
alter table public.user_goals
    add column if not exists onboarded_at timestamptz;
