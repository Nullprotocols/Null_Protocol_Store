# config.py - ENVIRONMENT VARIABLES READY (NO CODE EDIT REQUIRED)

import os

# ============================================
# 1. TELEGRAM BOT CREDENTIALS (FROM ENV)
# ============================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN environment variable is missing!")

OWNER_ID = int(os.getenv("OWNER_ID", "8104850843"))

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "NullProtocol_SuperSecret_2024")

BOT_MODE = os.getenv("BOT_MODE", "webhook")

# ============================================
# 2. SERVER & DEPLOYMENT (Render)
# ============================================
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://null-protocol-store.onrender.com")
PORT = int(os.getenv("PORT", "8080"))

# ============================================
# 3. DATABASE
# ============================================
DB_FILE = os.getenv("DB_FILE", "bot.db")

# ============================================
# 4. CACHE CONFIGURATION
# ============================================
REDIS_URL = os.getenv("REDIS_URL", None)
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# ============================================
# 5. AUTO-PING
# ============================================
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "240"))
ENABLE_SELF_PING = os.getenv("ENABLE_SELF_PING", "True").lower() == "true"

# ============================================
# 6. BRANDING
# ============================================
BRANDING = {
    "developer": os.getenv("BRANDING_DEVELOPER", "@Nullprotocol_x"),
    "powered_by": os.getenv("BRANDING_POWERED", "NULL PROTOCOL"),
    "support": os.getenv("BRANDING_SUPPORT", "@Nullprotocol_x"),
    "website": "https://t.me/Nullprotocol_x"
}

# ============================================
# 7. GLOBAL BLACKLIST
# ============================================
GLOBAL_BLACKLIST = [
    "copyright",
    "signature",
    "credit",
    "source"
]

# ============================================
# 8. FORCE JOIN CHANNELS
# ============================================
FORCE_JOIN_CHANNELS = [
    {"id": -1003090922367, "link": "https://t.me/all_data_here", "name": "All Data Here"},
    {"id": -1003698567122, "link": "https://t.me/osint_lookup", "name": "OSINT Lookup"},
    {"id": -1003672015073, "link": "https://t.me/legend_chats_osint", "name": "LEGEND CHATS"}
]

# ============================================
# 9. LOG CHANNEL
# ============================================
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003624886596"))

# ============================================
# 10. API ENDPOINTS CONFIGURATION
# ============================================
API_ENDPOINTS = {
    "num": {
        "name": "Phone Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://ayaanmods.site/number.php?key={api_key}&number={param}",
        "external_api_key": os.getenv("NUM_API_KEY", "annonymous"),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [
            "channel_name",
            "owner",
            "channel_link",
            "branding"
        ],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    },
    "tg": {
        "name": "Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username",
        "url_template": "https://sbsakib.eu.cc/api/Tg_username/?key={api_key}&username={param}",
        "external_api_key": os.getenv("TG_API_KEY", "Premium_User"),
        "param_name": "username",
        "param_example": "@InvalidAnand",
        "param_validation": r"^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "extra_blacklist": [
            "developer",
            "owner",
            "success",
            "key_status"
        ],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    }
}

# ============================================
# 11. API PLANS & PRICING
# ============================================
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

# ============================================
# 12. REFERRAL SYSTEM
# ============================================
REFERRAL_REWARD_CREDITS = int(os.getenv("REFERRAL_REWARD_CREDITS", "3"))

# ============================================
# 13. PREMIUM USER SETTINGS
# ============================================
PREMIUM_EXEMPT_FORCE_JOIN = os.getenv("PREMIUM_EXEMPT_FORCE_JOIN", "False").lower() == "true"

# ============================================
# 14. ADMIN / OWNER CONTACT
# ============================================
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@Nullprotocol_x")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Nullprotocol_x")

# ============================================
# 15. RATE LIMITING
# ============================================
DEFAULT_RATE_LIMIT_PER_MIN = int(os.getenv("DEFAULT_RATE_LIMIT", "80"))

# ============================================
# 16. DEBUG & LOGGING
# ============================================
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================
# PRINT CONFIRMATION
# ============================================
print("✅ CONFIG LOADED - NULL PROTOCOL API BOT")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"📢 Log Channel: {LOG_CHANNEL_ID}")
print(f"🔗 Force Join Channels: {len(FORCE_JOIN_CHANNELS)}")
print(f"💎 Branding: {BRANDING['developer']}")
