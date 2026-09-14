# Деплой на Render

Одним сервісом: FastAPI віддає і API, і зібраний фронтенд. Адреса перестає
ротуватись — саме через це новий користувач не міг повернутись після OAuth.

## 0. Перед пушем — перезібрати фронтенд

`frontend/dist` лежить у репозиторії навмисно: так Render не залежить від
наявності Node. Після будь-якої зміни інтерфейсу:

```bash
npm --prefix frontend run build && git add frontend/dist && git commit -m "збірка фронтенду"
```

## 1. Підготовка

Згенеруй ключ шифрування токенів, якщо його ще немає:

```bash
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

## 2. Створення сервісу

1. **render.com → New → Blueprint**, вкажи репозиторій — Render підхопить `render.yaml`.
   (Або New → Web Service вручну з командами з `render.yaml`.)
Якщо створюєш вручну (New → **Web Service**), поля такі:

| Поле | Значення |
|---|---|
| Language | Python 3 |
| Python Version | `3.12.8` — див. нижче |
| Branch | `main` |
| Root Directory | *порожньо* |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend` |
| Health Check Path | `/health` |

2. Заповни змінні, позначені `sync: false`:

| Змінна | Звідки взяти |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_BOT_USERNAME` | ім'я бота без `@` |
| `TELEGRAM_WEBAPP_SHORT_NAME` | short name з `/newapp` |
| `TOKEN_ENCRYPTION_KEY` | команда вище |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API |
| `GEMINI_API_KEY` | Google AI Studio |
| `PUBLIC_BACKEND_URL` | **адреса сервісу Render** — див. крок 3 |

3. Перший деплой впаде на `PUBLIC_BACKEND_URL`, якщо його ще немає. Це нормально.

### Якщо збірка падає на `pydantic-core`

Render за замовчуванням бере найновіший Python (зараз 3.14), для якого ще
немає готових колес `pydantic-core`. Pip намагається зібрати його з Rust і
падає на read-only файловій системі.

У репозиторії лежить `.python-version` з `3.12.8` — Render має його підхопити.
Якщо сервіс створений до цього коміту, додай змінну вручну:

```
PYTHON_VERSION=3.12.8
```

і запусти **Manual Deploy → Clear build cache & deploy**.

## 3. Прив'язка адреси

Render видасть `https://greencart-xxxx.onrender.com`.

1. Впиши її в `PUBLIC_BACKEND_URL` і передеплой.
2. З неї будується `redirect_uri` для OAuth Сільпо. Dynamic Client Registration
   перереєструється автоматично — вручну нічого робити не треба.

## 4. Telegram

```bash
cd backend && .venv/bin/python scripts/setup_bot.py --webapp-url https://greencart-xxxx.onrender.com
```

Скрипт виставить кнопку меню й webhook.

**Обов'язково вручну:** @BotFather → `/myapps` → обрати застосунок → **Edit Web App URL**
→ вставити ту саму адресу.

Це критично: посилання `t.me/<bot>/<app>` заморожене на момент реєстрації, і
саме на нього веде повернення після OAuth. Без цього кроку **новий користувач
не зайде**, навіть коли кнопка меню працює.

## 5. Міграції

Усі вісім уже застосовані до робочої бази Supabase. Для чистої бази:

```bash
for f in supabase/migrations/*.sql; do
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$f"
done
```

## 6. Перевірка наскрізь

1. `GET /health` → `{"status":"ok"}`
2. Telegram → кнопка меню бота → Mini App відкривається
3. «Підключити Сільпо» → браузер → вхід → **повернення в застосунок**
4. Головний екран показує можливості
5. План → обрати заміни → «Додати схвалене в кошик»
6. «Живі дані» → видно `silpo_add_or_update_cart_products` із міткою «запис»

## Особливості безкоштовного плану

Сервіс засинає після 15 хвилин без запитів; перший запит після сну займає
~30 секунд. Перед демо відкрий застосунок заздалегідь, щоб розбудити.
Фоновий дайджест вимкнено (`ENABLE_DIGEST=false`) — на free-плані він би
тримав сервіс у неспанні й вичерпав години.

## Нагадування «за командою» для зйомки демо

Дайджест можна надіслати гостю в потрібний момент двома способами:

- сам гість: «Ще» → «Надіслати нагадування в бот зараз»;
- член команди з іншого телефона: у чаті з ботом `/push @username_гостя`
  (або `/push <telegram_id>`). Працює лише для Telegram ID зі змінної
  `DEMO_ADMIN_IDS` на Render (через кому, напр. `123456789,987654321`).
  Свій ID можна дізнатись у @userinfobot.

Якщо у гостя жоден товар ще не «на порозі» циклу, повідомлення бере до трьох
найближчих товарів з увімкненим дзвіночком у «Вигоді». Без увімкнених
дзвіночків надсилати нема чого — увімкніть їх перед зйомкою.
