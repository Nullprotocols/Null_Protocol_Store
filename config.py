# config.py - FINAL COMPLETE VERSION - NO EDIT REQUIRED EXCEPT BOT TOKEN

import os

# ============================================
# 1. TELEGRAM BOT CREDENTIALS (ONLY THIS LINE NEEDS YOUR TOKEN)
# ============================================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # <--- BAS YAHAN APNA BOT TOKEN DAALO, BAAKI SAB READY HAI

# Main Owner ID (jo sab kuch control karega)
OWNER_ID = 8104850843

# Webhook Secret (internal security)
WEBHOOK_SECRET = "NullProtocol_SuperSecret_2024"

# Bot running mode: "polling" ya "webhook" (webhook recommended for speed)
BOT_MODE = "webhook"

# ============================================
# 2. SERVER & DEPLOYMENT (Render)
# ============================================
RENDER_EXTERNAL_URL = "https://null-protocol-store.onrender.com"
PORT = 8080

# ============================================
# 3. DATABASE
# ============================================
DB_FILE = "bot.db"

# ============================================
# 4. CACHE CONFIGURATION (In-Memory Fast Cache)
# ============================================
REDIS_URL = None  # Redis nahi use karna to None rakho
CACHE_TTL = 300  # 5 minutes

# ============================================
# 5. AUTO-PING (Keep Alive) - Har 4 Minute
# ============================================
SELF_PING_INTERVAL = 240
ENABLE_SELF_PING = True

# ============================================
# 6. BRANDING (Jo har API response mein dikhega)
# ============================================
BRANDING = {
    "developer": "@Nullprotocol_x",
    "powered_by": "NULL PROTOCOL",
    "support": "@Nullprotocol_x",
    "website": "https://t.me/Nullprotocol_x"
}

# ============================================
# 7. GLOBAL BLACKLIST (Sabhi API responses se yeh fields hata diye jayenge)
# ============================================
GLOBAL_BLACKLIST = [
    "copyright",
    "signature",
    "credit",
    "source"
]

# ============================================
# 8. FORCE JOIN CHANNELS (Jinhe join karna compulsory hai)
# ============================================
FORCE_JOIN_CHANNELS = [
    {"id": -1003090922367, "link": "https://t.me/all_data_here", "name": "All Data Here"},
    {"id": -1003698567122, "link": "https://t.me/osint_lookup", "name": "OSINT Lookup"},
    {"id": -1003672015073, "link": "https://t.me/legend_chats_osint", "name": "LEGEND CHATS"}
]

# ============================================
# 9. LOG CHANNEL (Jahan API key generation logs jayenge)
# ============================================
LOG_CHANNEL_ID = -1003624886596

# ============================================
# 10. API ENDPOINTS CONFIGURATION (Number Info + Telegram to Number)
# ============================================
API_ENDPOINTS = {
    "num": {
        "name": "Phone Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://ayaanmods.site/number.php?key={api_key}&number={param}",
        "external_api_key": "annonymous",
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
        "log_channel": -1003624886596,
        "enabled": True
    },
    "tg": {
        "name": "Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username",
        "url_template": "https://multi-endpoint-rootxindia.satyamrajsingh49.workers.dev/tgnum?key={api_key}&term={param}",
        "external_api_key": "demo",
        "param_name": "username",
        "param_example": "7445701268",
        "param_validation": r"^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "extra_blacklist": [
            "developer",
            "owner",
            "success",
            "key_status"
        ],
        "rate_limit_per_min": 80,
        "log_channel": -1003624886596,
        "enabled": True
    }
}

# ============================================
# 11. API PLANS & PRICING (Credits)
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
REFERRAL_REWARD_CREDITS = 3

# ============================================
# 13. PREMIUM USER SETTINGS
# ============================================
PREMIUM_EXEMPT_FORCE_JOIN = False

# ============================================
# 14. ADMIN / OWNER CONTACT
# ============================================
OWNER_USERNAME = "@Nullprotocol_x"
SUPPORT_USERNAME = "@Nullprotocol_x"

# ============================================
# 15. RATE LIMITING
# ============================================
DEFAULT_RATE_LIMIT_PER_MIN = 80

# ============================================
# 16. DEBUG & LOGGING
# ============================================
DEBUG = False
LOG_LEVEL = "INFO"

# ============================================
# PRINT CONFIRMATION (Bot start hote hi dikhega)
# ============================================
print("✅ CONFIG LOADED - NULL PROTOCOL API BOT")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"📢 Log Channel: {LOG_CHANNEL_ID}")
print(f"🔗 Force Join Channels: {len(FORCE_JOIN_CHANNELS)}")
print(f"💎 Branding: {BRANDING['developer']}")
