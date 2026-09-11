-- Налаштування гостя: режим агента і ціновий поріг.
--
-- Обидва поля живуть у user_goals, бо це та сама сутність «як агент має
-- поводитися зі мною». goal лишається про харчові норми (Міффлін-Сан-Жеор),
-- mode — про продуктову поведінку: що виносити вгору і що вмикати заздалегідь.
alter table public.user_goals
    -- health | saving | analytics | auto. Дефолт 'auto': ~40% нейтральні до
    -- health-скорингу, тож пропуск онбордингу має давати робочий режим.
    add column if not exists mode text not null default 'auto',
    -- Частка, а не відсоток: 0.05 = «до 5%». NULL = «без обмежень».
    -- Дефолт 0.05 — найбільша група в опитуванні (30%).
    add column if not exists price_tolerance numeric(4,3) default 0.05,
    -- Сімейний контекст: {"lactoza":"warn","nuts":"block"}.
    -- Алерген блокує завжди; тут гість може лише посилити м'яке обмеження.
    add column if not exists restriction_strictness jsonb not null default '{}'::jsonb;

comment on column public.user_goals.price_tolerance is
    'Максимальне прийнятне подорожчання альтернативи. NULL = без обмежень.';
