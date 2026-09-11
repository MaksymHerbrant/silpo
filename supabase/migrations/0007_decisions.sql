-- Метрика цінності продукту: що ми запропонували і що гість прийняв.
--
-- Це єдина цифра, яку не можна намалювати в презентації. Не «користувач
-- подивився графік», а «користувач змінив покупку».
--
-- price_delta зберігаємо на момент ПОКАЗУ: ціни змінюються, і рахувати
-- економію заднім числом за новими цінами було б підтасовкою.
create table if not exists public.decisions (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references public.users(id) on delete cascade,
    -- safety | preference | promo | health | alternative | reminder
    kind        text not null,
    slug        text,
    alt_slug    text,
    title       text,
    price_delta numeric(10,2),
    shown_at    timestamptz not null default now(),
    accepted    boolean,
    decided_at  timestamptz
);
create index if not exists decisions_user_idx on public.decisions(user_id, shown_at desc);
-- Відкрита пропозиція на ту саму пару «товар → заміна» має бути одна:
-- інакше кожна перебудова плану роздувала б знаменник і псувала відсоток.
create unique index if not exists decisions_open_uniq
    on public.decisions(user_id, kind, coalesce(slug, ''), coalesce(alt_slug, ''))
    where accepted is null;
alter table public.decisions enable row level security;
