-- Збережений результат довгих побудов.
--
-- Проблема, яку це закриває: кожне відкриття застосунку заново читало чеки й
-- картки товарів — понад тридцять викликів MCP, щоб показати рівно те саме.
-- Кеш був лише в памʼяті процесу, тож перезапуск бекенду або 15 хвилин
-- бездіяльності знецінювали всю роботу.
--
-- Тепер результат живе в базі, а перебудова відбувається у двох випадках:
--   1. гість сам натиснув «оновити»;
--   2. фонова перевірка побачила НОВИЙ чек.
create table if not exists public.job_cache (
    user_id    uuid not null references public.users(id) on delete cascade,
    -- plan_next | insights | nutrition:week | usual …
    name       text not null,
    -- Відбиток чеків, з яких зібрано результат. Змінився — дані застаріли.
    signature  text,
    built_at   timestamptz not null default now(),
    -- Коли востаннє питали Сільпо, чи є новий чек
    checked_at timestamptz,
    payload    jsonb not null,
    primary key (user_id, name)
);
alter table public.job_cache enable row level security;
