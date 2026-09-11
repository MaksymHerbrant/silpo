-- Цикли покупок і стеження за цінами.
--
-- Цикл рахується з ФАКТИЧНИХ дат покупок товару (медіана проміжків), а не з
-- категорійного припущення. Категорія лишається запасним варіантом, коли
-- товар куплено лише раз і проміжків ще немає.
create table if not exists public.product_cycles (
    user_id      uuid not null references public.users(id) on delete cascade,
    slug         text not null,
    name         text,
    -- Спостережений цикл у днях; NULL = ще нема з чого рахувати
    cycle_days   integer,
    -- Ручне уточнення від гостя. Має пріоритет над спостереженим.
    cycle_override integer,
    last_bought  date,
    next_due     date,
    reminder_on  boolean not null default false,
    updated_at   timestamptz not null default now(),
    primary key (user_id, slug)
);
create index if not exists product_cycles_due_idx
    on public.product_cycles(user_id, next_due);
alter table public.product_cycles enable row level security;

-- Стеження за цінами.
--
-- Свідомо стежимо за тим, що гість РЕГУЛЯРНО КУПУЄ, а не за списком «обране»:
-- silpo_get_my_favorites віддає помилку на боці Сільпо, та й куплене — це
-- реальна поведінка, а обране може бути порожнім або забутим.
create table if not exists public.price_watch (
    user_id     uuid not null references public.users(id) on delete cascade,
    slug        text not null,
    product_id  text,
    name        text,
    last_price  numeric(10,2),
    min_price   numeric(10,2),
    seen_at     timestamptz not null default now(),
    primary key (user_id, slug)
);
alter table public.price_watch enable row level security;

-- Коли востаннє слали дайджест. В автопілоті — не частіше разу на тиждень.
alter table public.user_goals
    add column if not exists digest_sent_at timestamptz;
