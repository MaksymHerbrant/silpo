-- Dynamic Client Registration (RFC 7591).
-- MCP Сільпо не видає client_id заздалегідь: клієнт реєструється сам через
-- POST https://mcp.silpo.ua/register. Реєстрація прив'язана до redirect_uri,
-- тому зберігаємо її й перевикористовуємо між рестартами бекенду.
create table if not exists public.oauth_clients (
    id             uuid primary key default gen_random_uuid(),
    issuer         text not null,
    redirect_uri   text not null,
    client_id      text not null,
    client_secret  text,               -- ciphertext (Fernet), якщо сервер його видав
    auth_method    text not null default 'none',
    raw_response   jsonb,
    created_at     timestamptz not null default now(),
    unique (issuer, redirect_uri)
);

alter table public.oauth_clients enable row level security;
