from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""          # без @, напр. nutrikoshyk_bot
    telegram_webapp_short_name: str = "app"  # t.me/<bot>/<app>
    # initData вважається протухлим після N секунд (Telegram рекомендує <= 24h)
    telegram_initdata_max_age: int = 86400
    # secret_token для setWebhook: без нього будь-хто може слати нам фейкові апдейти
    telegram_webhook_secret: str = "change-me-webhook-secret"

    # --- Сесія Mini App ---
    session_secret: str = "dev-insecure-change-me"
    session_ttl_seconds: int = 60 * 60 * 12

    # --- Supabase ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # --- Шифрування MCP-токенів (Fernet key, base64 32 bytes) ---
    token_encryption_key: str = ""

    # --- MCP Сільпо ---
    silpo_mcp_url: str = "https://mcp.silpo.ua/mcp"
    silpo_oauth_client_id: str = ""
    silpo_oauth_client_secret: str = ""      # PKCE-only клієнт може не мати секрету
    silpo_oauth_scope: str = ""
    # Якщо discovery недоступний — використовуються ці значення
    silpo_oauth_issuer: str = "https://mcp.silpo.ua"
    silpo_oauth_authorize_url: str = ""
    silpo_oauth_token_url: str = ""

    # Публічний URL бекенду (потрібен для OAuth redirect_uri)
    public_backend_url: str = "http://localhost:8000"
    public_frontend_url: str = "http://localhost:5173"

    # --- LLM: gemini | anthropic | none ---
    # Числа рахує детермінований код, модель лише планує дії й формулює текст,
    # тому провайдер — змінна деталь, а не архітектурне рішення.
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    enable_llm_explanations: bool = True

    # --- Режими ---
    # demo_mode=true => MCP підмінюється фікстурами (для офлайн-розробки UI)
    demo_mode: bool = False
    cors_origins: str = "*"

    # --- Rate limiting для MCP ---
    mcp_min_interval_ms: int = 250      # затримка між викликами tools/call
    mcp_max_retries: int = 5
    mcp_backoff_base_ms: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
