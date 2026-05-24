# config.py - FINAL PRODUCTION VERSION (ULTRA FAST - ALL FEATURES)

import os

# ------------------------------------------------------------
# 1. TELEGRAM BOT
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN missing!")

OWNER_ID = int(os.getenv("OWNER_ID", "8104850843"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "NullProtocol_SuperSecret_2024")
BOT_MODE = os.getenv("BOT_MODE", "webhook")

# ------------------------------------------------------------
# 2. SERVER
# ------------------------------------------------------------
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://null-protocol-app-store.onrender.com")
PORT = int(os.getenv("PORT", "10000"))

# ------------------------------------------------------------
# 3. DATABASE (PostgreSQL – internal URL from env)
# ------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL missing!")
# asyncpg requires "postgresql://" prefix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ------------------------------------------------------------
# 4. CACHE (In‑memory, Redis optional)
# ------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", None)
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds

# ------------------------------------------------------------
# 5. AUTO-PING (Keep alive)
# ------------------------------------------------------------
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "240"))
ENABLE_SELF_PING = os.getenv("ENABLE_SELF_PING", "True").lower() == "true"

# ------------------------------------------------------------
# 6. BRANDING
# ------------------------------------------------------------
BRANDING = {
    "developer": os.getenv("BRANDING_DEVELOPER", "@Nullprotocol_x"),
    "powered_by": os.getenv("BRANDING_POWERED", "NULL PROTOCOL"),
    "support": os.getenv("BRANDING_SUPPORT", "@Nullprotocol_x"),
    "website": "https://t.me/Nullprotocol_x"
}

# ------------------------------------------------------------
# 7. GLOBAL BLACKLIST (fields to strip)
# ------------------------------------------------------------
GLOBAL_BLACKLIST = [
    "copyright", "signature", "credit", "source"
]

# ------------------------------------------------------------
# 8. FORCE JOIN CHANNELS
# ------------------------------------------------------------
FORCE_JOIN_CHANNELS = [
    {"id": -1003090922367, "link": "https://t.me/all_data_here", "name": "All Data Here"},
    {"id": -1003698567122, "link": "https://t.me/osint_lookup", "name": "OSINT Lookup"},
    {"id": -1003672015073, "link": "https://t.me/legend_chats_osint", "name": "LEGEND CHATS"}
]

# ------------------------------------------------------------
# 9. LOG CHANNEL
# ------------------------------------------------------------
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003624886596"))

# ------------------------------------------------------------
# 10. API ENDPOINTS (Phone & Telegram Username)
# ------------------------------------------------------------
API_ENDPOINTS = {
    "num": {
        "name": "Phone Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("NUM_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["credits"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    },
    "tg": {
        "name": "Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username",
        "url_template": "https://rootx-osint.in/?type=tg_num&key={api_key}&query={param}",
        "external_api_key": os.getenv("TG_API_KEY", "null_protocol"),
        "param_name": "username",
        "param_example": "@InvalidAnand",
        "param_validation": r"^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "extra_blacklist": [
            "is_verified", "id", "has_profile_pic", "first_name",
            "is_scam", "credit", "common_chats", "bio", "username", "target",
            "is_fake", "type", "public_view", "is_bot"
        ],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    }
}

# ------------------------------------------------------------
# 11. SUBSCRIPTION PLANS & PRICING
# ------------------------------------------------------------
DEFAULT_PLANS = {
    "num": {
        "weekly": {"credits": 15, "days": 7},
        "monthly": {"credits": 30, "days": 30}
    },
    "tg": {
        "weekly": {"credits": 15, "days": 7},
        "monthly": {"credits": 30, "days": 30}
    }
}

# ------------------------------------------------------------
# 12. REFERRAL SYSTEM
# ------------------------------------------------------------
REFERRAL_REWARD_CREDITS = int(os.getenv("REFERRAL_REWARD_CREDITS", "3"))

# ------------------------------------------------------------
# 13. PREMIUM USER SETTINGS
# ------------------------------------------------------------
PREMIUM_EXEMPT_FORCE_JOIN = os.getenv("PREMIUM_EXEMPT_FORCE_JOIN", "False").lower() == "true"

# ------------------------------------------------------------
# 14. CONTACTS
# ------------------------------------------------------------
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@Nullprotocol_x")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Nullprotocol_x")

# ------------------------------------------------------------
# 15. DEFAULT RATE LIMIT (for new keys)
# ------------------------------------------------------------
DEFAULT_RATE_LIMIT_PER_MIN = int(os.getenv("DEFAULT_RATE_LIMIT", "80"))

# ------------------------------------------------------------
# 16. BACKUP SETTINGS (Daily CSV to owner DM)
# ------------------------------------------------------------
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", str(OWNER_ID)))  # default: owner

# ------------------------------------------------------------
# 17. DEBUG & LOGGING
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

print("✅ CONFIG LOADED - POSTGRESQL + BACKUP + CUSTOM KEYS (ULTRA FAST)")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"📢 Log Channel: {LOG_CHANNEL_ID}")
print(f"💾 Database: PostgreSQL (internal URL)")
