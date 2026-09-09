# 🧺 Нутрі-Кошик

Telegram **Mini App** для хакатону «Сільпо AI Factory». Не чат-бот: користувач працює з
екранами й графіками всередині Telegram, а дані про покупки надходять напряму з
офіційного MCP Сільпо — вручну вносити продукти не треба.

| Що показує | Звідки бере |
|---|---|
| Рейтинг здоров'я кошика 0–100 і клас A–E | `silpo_get_my_shopping_cart` → `silpo_get_shopping_cart_by_id` → `silpo_get_product_details` |
| Розклад БЖУ і доданого цукру | харчова цінність товарів кошика |
| Попередження про алергени | `silpo_get_my_food_restrictions` × склад товару |
| Тижневий тренд рейтингу | `silpo_get_my_online_orders`, згруповані по тижнях |
| Розумні свопи (пріоритет власних марок) | `silpo_get_similar_products` |
| Застосування заміни в кошику | `silpo_add_or_update_cart_products` (write) |

---

## Структура

```
backend/    FastAPI: MCP-клієнт, OAuth 2.1+PKCE, скоринг, API
  app/nutrition/   детермінований Health Score + парсер + алергени
  app/mcp/         MCP-клієнт, OAuth, rate limit, лог JSON-RPC, фікстури
  scripts/         probe_mcp.py (розвідка схеми), smoke_demo.py, setup_bot.py
frontend/   React + Vite + Recharts + Telegram Web App SDK
supabase/   SQL-міграції
docs/       методика скорингу, сценарій демо
```

---

## Швидкий старт (локально, без живого MCP)

```bash
# 1. Бекенд
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example .env          # заповни TELEGRAM_BOT_TOKEN, TOKEN_ENCRYPTION_KEY
.venv/bin/python scripts/smoke_demo.py    # наскрізний тест на фікстурах
DEMO_MODE=true .venv/bin/uvicorn app.main:app --reload --port 8000

# 2. Фронтенд
cd ../frontend
npm install
echo 'VITE_API_BASE_URL=http://localhost:8000' > .env
npm run dev
```

`DEMO_MODE=true` підміняє MCP фікстурами (`backend/app/mcp/fixtures.py`) — щоб робити UI без
живого акаунта. Для демо журі обов'язково `DEMO_MODE=false`.

Ключ шифрування токенів:

```bash
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

Supabase: виконай `supabase/migrations/0001_init.sql` у SQL-редакторі проєкту
(або `supabase db push`). Якщо `SUPABASE_URL` порожній, бекенд працює на in-memory
сховищі — зручно для розробки, але тренд і метрика свопів не переживуть рестарт.

---

## Підключення Telegram

1. **@BotFather** → `/newbot` → отримай токен → `TELEGRAM_BOT_TOKEN`.
2. **@BotFather** → `/newapp` → обери бота → задай *short name* (напр. `app`) і URL фронтенду.
   Short name йде в `TELEGRAM_WEBAPP_SHORT_NAME` — без нього не працює deep link
   `t.me/<bot>/<app>?startapp=<token>`, через який користувач повертається після OAuth.
3. `cd backend && .venv/bin/python scripts/setup_bot.py --webapp-url https://<фронтенд>`
   (виставляє кнопку меню; жодної діалогової логіки в бота немає — він лише точка входу).

Локальний https для тесту в Telegram: `cloudflared tunnel --url http://localhost:5173`
(або ngrok) — Telegram не відкриє Mini App по http.

### Авторизація користувача

Фронтенд шле `Telegram.WebApp.initData` у `POST /auth/telegram`. Бекенд валідує підпис:

```
secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
expected   = HMAC_SHA256(key=secret_key, msg=data_check_string)   # пари key=value, \n, відсортовані
```

плюс перевіряє свіжість `auth_date`. Без цієї перевірки будь-хто підробив би `telegram_id`.
Реалізація — [telegram_auth.py](backend/app/security/telegram_auth.py), негативний кейс
покритий у [smoke_demo.py](backend/scripts/smoke_demo.py).

---

## Підключення MCP Сільпо

Ендпоінт — виключно `https://mcp.silpo.ua/mcp` (Streamable HTTP), авторизація OAuth 2.1 + PKCE.

**`client_id` заповнювати не треба.** Сільпо підтримує Dynamic Client Registration
(RFC 7591): бекенд читає метадані, сам робить `POST https://mcp.silpo.ua/register`,
отримує `client_id` і кешує його в таблиці `oauth_clients` (прив'язка до `redirect_uri`).
Єдина обов'язкова змінна — `PUBLIC_BACKEND_URL`, з якої будується
`redirect_uri = <PUBLIC_BACKEND_URL>/auth/silpo/callback`. Зміниш публічний URL —
бекенд перереєструється автоматично.

Перевірені наживо метадані (`/.well-known/oauth-protected-resource` →
`/.well-known/oauth-authorization-server`):

| | |
|---|---|
| issuer | `https://mcp.silpo.ua` |
| authorize | `https://mcp.silpo.ua/authorize` |
| token | `https://mcp.silpo.ua/token` |
| register | `https://mcp.silpo.ua/register` |
| PKCE | `S256` |
| auth methods | `client_secret_basic`, `client_secret_post`, `none` (ми реєструємось як `none`) |

**Флоу всередині Telegram** (WebView нестабільно тримає сторонні OAuth-popup'и):

```
Mini App ──POST /auth/silpo/start──► бекенд генерує PKCE+state, віддає authorize_url
Mini App ──Telegram.WebApp.openLink(authorize_url)──► ЗОВНІШНІЙ браузер → auth.silpo.ua
браузер  ──GET /auth/silpo/callback?code&state──► бекенд міняє code на токени,
                                                  шифрує (Fernet), кладе в Supabase
бекенд   ──302 t.me/<bot>/<app>?startapp=<one-time>──► Mini App відкривається знову
Mini App ──POST /auth/telegram (initData зі start_param)──► сесія вже з під'єднаним Сільпо
```

> Це найризикованіша частина інтеграції — протестуй перехід окремо на реальному пристрої
> (Android і iOS поводяться по-різному) до запису демо.

**Токен ніколи не потрапляє у фронтенд.** У React є лише прапорець `silpo_connected`;
`access_token`/`refresh_token` лежать зашифрованими в `silpo_oauth_tokens`, ключ — в env бекенду.

### Обмеження, які оброблені в коді

| Ситуація | Де | Що робимо |
|---|---|---|
| `429 Too Many Requests` | [ratelimit.py](backend/app/mcp/ratelimit.py) | черга per-user + пауза `MCP_MIN_INTERVAL_MS` між викликами + експоненційний backoff з jitter |
| Кошик на 20+ товарів | [cart_analysis.py](backend/app/services/cart_analysis.py) | `silpo_get_product_details` викликається послідовно, а не 20 паралельних запитів |
| `401` | [client.py](backend/app/mcp/client.py) | refresh-флоу і один повтор; якщо refresh недоступний — просимо перепід'єднати |
| `403` | [client.py](backend/app/mcp/client.py) | `McpToolForbidden`, без ретраїв, зрозуміле повідомлення |
| Немає харчової цінності | [parser.py](backend/app/nutrition/parser.py), [score.py](backend/app/nutrition/score.py) | товар позначається «дані відсутні» й **не** входить у скор; нулі не підставляються |

### Схема відповідей MCP

Ми **не вигадували** структуру JSON: парсер шукає поля за синонімами ключів і за парами
`{name, value}`, тому переживає різні формати. Перед демо звір із реальністю:

```bash
cd backend
.venv/bin/python scripts/probe_mcp.py --user <uuid> --tools
.venv/bin/python scripts/probe_mcp.py --user <uuid> --cart
.venv/bin/python scripts/probe_mcp.py --user <uuid> --product <id>
```

Скрипт друкує сирий JSON, плаский зріз схеми і те, що з нього розпізнав парсер (включно зі
списком відсутніх полів). Якщо якийсь нутрієнт не знайшовся — додай його ключ у
`KEY_SYNONYMS` в [parser.py](backend/app/nutrition/parser.py); решта коду не змінюється.

---

## API

| Метод | Шлях | Призначення |
|---|---|---|
| POST | `/auth/telegram` | валідація initData, видача сесії |
| POST | `/auth/silpo/start` | URL авторизації Сільпо (відкривається через `openLink`) |
| GET | `/auth/silpo/callback` | обмін code → токени, редірект у Mini App |
| GET | `/auth/silpo/status` | під'єднано чи ні (без самого токена) |
| GET | `/cart/analysis` | скор, БЖУ, цукор, товари, алергени, пояснення |
| GET | `/cart/allergens` | лише обмеження й попередження |
| GET | `/trends/weekly` | історія рейтингів по тижнях |
| GET | `/swaps/suggestions` | пропозиції заміни + метрика прийняття |
| POST | `/swaps/{id}/apply` | застосувати своп (write-виклик MCP) |
| POST | `/swaps/{id}/decline` | відхилити (для метрики «% прийнятих свопів») |
| GET | `/debug/mcp-log` | сирі JSON-RPC виклики за сесію |
| GET | `/debug/tools` | `tools/list` |

Swagger: `http://localhost:8000/docs`.

---

## Health Score

Детермінована евристика в стилі **Nutri-Score** (nutrient profiling): негативні бали за
енергію, цукри, насичені жири й натрій; позитивні — за клітковину й білок. Кошик зводиться
до середньозваженого по масі профілю на 100 г, далі — та сама шкала → 0–100 і клас A–E.

**Claude не рахує жодного числа.** LLM використовується лише для людських формулювань і
отримує вже готові числа ([explain.py](backend/app/llm/explain.py)); причини свопів взагалі
детерміновані. Деталі й обмеження методики — [docs/methodology.md](docs/methodology.md).

---

## Деплой для демо

- **Бекенд** (Railway / Fly / Render): `uvicorn app.main:app --host 0.0.0.0 --port $PORT`,
  усі змінні з `.env.example`, `PUBLIC_BACKEND_URL` = публічний https URL.
- **Фронтенд** (Vercel / Netlify / Cloudflare Pages): `npm run build`, папка `dist`,
  змінна `VITE_API_BASE_URL`.
- `CORS_ORIGINS` = домен фронтенду.
- Після деплою: `setup_bot.py --webapp-url https://<фронтенд>` і `/newapp` у BotFather.

Сценарій запису демо — [docs/demo-script.md](docs/demo-script.md).

## Відповідність вимогам хакатону

- Єдине джерело даних — `https://mcp.silpo.ua/mcp`; сторонніх API Сільпо немає.
- MCP-токени зберігаються серверно й зашифровано, у клієнтський код не потрапляють.
- Демо показує `tools/list`, кілька read-tools і один write (`silpo_add_or_update_cart_products`).
- Екран «MCP-лог» показує сирі JSON-RPC виклики наживо.
