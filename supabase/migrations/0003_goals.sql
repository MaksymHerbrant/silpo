-- Ціль користувача й розраховані норми.
-- Стать і дата народження приходять із silpo_get_my_profile, решту питаємо
-- в онбордингу (4 питання). Норми рахуються детерміновано (Міффлін-Сан-Жеор).
create table if not exists public.user_goals (
    user_id        uuid primary key references public.users(id) on delete cascade,
    goal           text not null,              -- lose | maintain | gain | health
    weight_kg      numeric(5,1),
    height_cm      numeric(5,1),
    activity       text not null default 'moderate',  -- sedentary|light|moderate|high|athlete
    sex            text,                        -- male | female (з профілю Сільпо)
    birthday       date,                        -- з профілю Сільпо
    household_size integer not null default 1,
    weekly_budget  numeric(10,2),
    -- Розраховані норми на день (кешуємо, щоб не рахувати щоразу)
    target_kcal    integer,
    target_protein integer,
    target_fat     integer,
    target_carbs   integer,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

alter table public.user_goals enable row level security;

-- Зібрані агентом кошики: що запропонували, що гість прийняв
create table if not exists public.basket_plans (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references public.users(id) on delete cascade,
    created_at   timestamptz not null default now(),
    budget       numeric(10,2),
    total_price  numeric(10,2),
    items_json   jsonb not null,
    coverage     jsonb,          -- скільки % норм закриває
    applied      boolean,        -- чи додав гість у кошик
    applied_at   timestamptz
);
create index if not exists basket_plans_user_idx on public.basket_plans(user_id, created_at desc);
alter table public.basket_plans enable row level security;
