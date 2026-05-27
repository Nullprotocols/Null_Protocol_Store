# config.py - UPGRADED PRODUCTION VERSION
# All 19 APIs + Har API ka alag plan + Google Sheets (env var)

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
# 3. DATABASE (PostgreSQL)
# ------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL missing!")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ------------------------------------------------------------
# 4. CACHE
# ------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", None)
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# ------------------------------------------------------------
# 5. AUTO-PING
# ------------------------------------------------------------
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "240"))
ENABLE_SELF_PING = os.getenv("ENABLE_SELF_PING", "True").lower() == "true"

# ------------------------------------------------------------
# 6. BRANDING
# ------------------------------------------------------------
BRANDING = {
    "developer": os.getenv("BRANDING_DEVELOPER", "@Nullprotocol_x"),
    "powered_by": os.getenv("BRANDING_POWERED", "NULL PROTOCOL"),
    "support": os.getenv("BRANDING_SUPPORT", "https://t.me/osint_father_NP"),
    "website": "https://t.me/Nullprotocol_x"
}

# ------------------------------------------------------------
# 7. GLOBAL BLACKLIST
# ------------------------------------------------------------
GLOBAL_BLACKLIST = [
    "copyright", "signature", "credit", "source",
    "developer", "powered_by", "support", "website"
]

# ------------------------------------------------------------
# 8. FORCE JOIN CHANNELS
# ------------------------------------------------------------
FORCE_JOIN_CHANNELS = [
    {"id": -1003090922367, "link": "https://t.me/all_data_here",        "name": "All Data Here"},
    {"id": -1003698567122, "link": "https://t.me/osint_lookup",         "name": "OSINT Lookup"},
    {"id": -1003672015073, "link": "https://t.me/legend_chats_osint",   "name": "LEGEND CHATS"}
]

# ------------------------------------------------------------
# 9. LOG CHANNEL
# ------------------------------------------------------------
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003624886596"))

# ------------------------------------------------------------
# 10. API ENDPOINTS  (19 APIs — har ek ka alag plan)
# ------------------------------------------------------------
_BASE = "https://anuapi.netlify.app/.netlify/functions/api"
_KEY  = os.getenv("ANUAPI_KEY", "")   # single upstream key for all anuapi endpoints

API_ENDPOINTS = {

    # ── TELECOM ──────────────────────────────────────────────
    "num": {
        "name": "📞 Phone Number Info",
        "description": "Get basic info about a phone number",
        "url_template": f"{_BASE}/Number?Number={{param}}&key={{api_key}}",
        "external_api_key": os.getenv("NUM_API_KEY", _KEY),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp", "proxy", "input"],
        "rate_limit_per_min": 80,
        "category": "telecom",
        "enabled": True,
    },
    "mobile": {
        "name": "📱 Mobile Number Lookup",
        "description": "Detailed mobile number intelligence",
        "url_template": f"{_BASE}/mobile?number={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp", "proxy"],
        "rate_limit_per_min": 80,
        "category": "telecom",
        "enabled": True,
    },
    "vi": {
        "name": "🟣 Vi SIM Info & Photo",
        "description": "Vi SIM subscriber info with photo",
        "url_template": f"{_BASE}/photo?/vi={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp"],
        "rate_limit_per_min": 60,
        "category": "telecom",
        "enabled": True,
    },
    "vi2": {
        "name": "🟣 Vi SIM Info (v2)",
        "description": "Vi SIM subscriber details (alternate endpoint)",
        "url_template": f"{_BASE}/v4?Vi%20photo={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp"],
        "rate_limit_per_min": 60,
        "category": "telecom",
        "enabled": True,
    },

    # ── IDENTITY ─────────────────────────────────────────────
    "aadhaar": {
        "name": "🪪 Aadhaar Lookup",
        "description": "Aadhaar card details",
        "url_template": f"{_BASE}/aadhaar?id={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "aadhaar",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "identity",
        "enabled": True,
    },
    "pan": {
        "name": "💳 PAN Card Lookup",
        "description": "PAN card holder details",
        "url_template": f"{_BASE}/pan?pan={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "pan",
        "param_example": "ABCDE1234F",
        "param_validation": r"^[A-Z]{5}\d{4}[A-Z]$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "identity",
        "enabled": True,
    },
    "rashan": {
        "name": "🍚 Ration Card Lookup",
        "description": "Ration card details via Aadhaar",
        "url_template": f"{_BASE}/rashan?aadhaar={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "aadhaar",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "identity",
        "enabled": True,
    },

    # ── VEHICLE ──────────────────────────────────────────────
    "vehicle": {
        "name": "🚗 Vehicle Registration",
        "description": "Vehicle RC details by registration number",
        "url_template": f"{_BASE}/vehicle?registration={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "registration",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "category": "vehicle",
        "enabled": True,
    },
    "vehicle2num": {
        "name": "🚗➡️📞 Vehicle to Number",
        "description": "Get owner phone number from vehicle registration",
        "url_template": f"{_BASE}/v2?query={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "registration",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Za-z]{2}\d{2}[A-Za-z]{1,2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "vehicle",
        "enabled": True,
    },
    "vehicle_backup": {
        "name": "🚗💾 Vehicle Backup",
        "description": "Vehicle backup data lookup",
        "url_template": f"{_BASE}/v3?Vehicle%20Backup={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "registration",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Za-z]{2}\d{2}[A-Za-z]{1,2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "vehicle",
        "enabled": True,
    },
    "fastag": {
        "name": "🏷️ FASTag Lookup",
        "description": "FASTag details by vehicle registration",
        "url_template": f"{_BASE}/fastag?vrn={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "registration",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Za-z]{2}\d{2}[A-Za-z]{1,2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "vehicle",
        "enabled": True,
    },
    "challan": {
        "name": "🚦 Challan Check",
        "description": "Traffic challan by vehicle registration",
        "url_template": f"{_BASE}/challan?vrn={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "registration",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Za-z]{2}\d{2}[A-Za-z]{1,2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "vehicle",
        "enabled": True,
    },
    "drive": {
        "name": "🪪 Driving License",
        "description": "Driving license details lookup",
        "url_template": f"{_BASE}/drive?drive={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "license",
        "param_example": "UP1420110012345",
        "param_validation": r"^[A-Z]{2}\d{2,4}\d{7,11}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "vehicle",
        "enabled": True,
    },

    # ── FINANCE ──────────────────────────────────────────────
    "upi": {
        "name": "💸 UPI Lookup",
        "description": "UPI VPA / ID details",
        "url_template": f"{_BASE}/upi?id={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "upi_id",
        "param_example": "user@upi",
        "param_validation": r"^[\w.\-]+@[\w]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "category": "finance",
        "enabled": True,
    },
    "upi2": {
        "name": "💸 UPI Lookup v2",
        "description": "UPI VPA details (alternate endpoint)",
        "url_template": f"{_BASE}/upi2?id={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "upi_id",
        "param_example": "user@upi",
        "param_validation": r"^[\w.\-]+@[\w]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "category": "finance",
        "enabled": True,
    },
    "gst": {
        "name": "🧾 GST Lookup",
        "description": "GST number details",
        "url_template": f"{_BASE}/gst?number={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "gst",
        "param_example": "27ABCDE1234F1Z5",
        "param_validation": r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "finance",
        "enabled": True,
    },
    "ifsc": {
        "name": "🏦 IFSC Lookup",
        "description": "Bank branch details by IFSC code",
        "url_template": f"{_BASE}/ifsc?code={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "ifsc",
        "param_example": "SBIN0001234",
        "param_validation": r"^[A-Z]{4}0[A-Z0-9]{6}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 100,
        "category": "finance",
        "enabled": True,
    },
    "gas": {
        "name": "⛽ Gas Connection Lookup",
        "description": "Gas consumer details by mobile number",
        "url_template": f"{_BASE}/gas?num={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "finance",
        "enabled": True,
    },

    # ── SOCIAL / DIGITAL ─────────────────────────────────────
    "tg": {
        "name": "✈️ Telegram Username → Number",
        "description": "Get phone number from Telegram username or user ID",
        "url_template": "https://rootx-osint.in/?type=tg_num&key={api_key}&query={param}",
        "external_api_key": os.getenv("TG_API_KEY", "null_protocol"),
        "param_name": "username",
        "param_example": "@mrmeowmeow3 or 123456789",
        "param_validation": r"^(@?[a-zA-Z][a-zA-Z0-9_]{4,31}|\d+)$",
        "extra_blacklist": ["expiry", "req_total", "req_left"],
        "rate_limit_per_min": 80,
        "category": "social",
        "enabled": True,
    },
    "telegram": {
        "name": "✈️ Telegram User Lookup",
        "description": "Telegram user details by username",
        "url_template": f"{_BASE}/telegram?user={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "username",
        "param_example": "username",
        "param_validation": r"^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "extra_blacklist": ["expiry"],
        "rate_limit_per_min": 80,
        "category": "social",
        "enabled": True,
    },
    "email": {
        "name": "📧 Email Lookup",
        "description": "Email address intelligence",
        "url_template": f"{_BASE}/email?address={{param}}&key={{api_key}}",
        "external_api_key": _KEY,
        "param_name": "email",
        "param_example": "test@example.com",
        "param_validation": r"^[\w.%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "category": "social",
        "enabled": True,
    },
}

# ── CATEGORY LABELS (for Telegram menus) ──────────────────────
API_CATEGORIES = {
    "telecom":  "📡 Telecom",
    "identity": "🪪 Identity",
    "vehicle":  "🚗 Vehicle",
    "finance":  "💰 Finance",
    "social":   "🌐 Social / Digital",
}

# ------------------------------------------------------------
# 11. PLANS  — weekly (15cr/7d) & monthly (30cr/30d) per API
# ------------------------------------------------------------
DEFAULT_PLANS = {
    api_key: {
        "weekly":  {"credits": 15, "days": 7},
        "monthly": {"credits": 30, "days": 30},
    }
    for api_key in API_ENDPOINTS
}

# ------------------------------------------------------------
# 12. REFERRAL
# ------------------------------------------------------------
REFERRAL_REWARD_CREDITS = int(os.getenv("REFERRAL_REWARD_CREDITS", "3"))

# ------------------------------------------------------------
# 13. PREMIUM
# ------------------------------------------------------------
PREMIUM_EXEMPT_FORCE_JOIN = os.getenv("PREMIUM_EXEMPT_FORCE_JOIN", "False").lower() == "true"

# ------------------------------------------------------------
# 14. CONTACTS
# ------------------------------------------------------------
OWNER_USERNAME  = os.getenv("OWNER_USERNAME",  "@Nullprotocol_x")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Nullprotocol_x")

# ------------------------------------------------------------
# 15. RATE LIMIT
# ------------------------------------------------------------
DEFAULT_RATE_LIMIT_PER_MIN = int(os.getenv("DEFAULT_RATE_LIMIT", "80"))

# ------------------------------------------------------------
# 16. BACKUP
# ------------------------------------------------------------
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", str(OWNER_ID)))

# ------------------------------------------------------------
# 17. GOOGLE SHEETS  — env variable ONLY
# ------------------------------------------------------------
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")   # Must be set in environment
if not GOOGLE_SHEET_ID:
    import warnings
    warnings.warn("⚠️  GOOGLE_SHEET_ID not set — Sheets logging will be disabled.")

GSHEET_CREDS = os.getenv("GSHEET_CREDS", "")  # base64-encoded service account JSON

# ------------------------------------------------------------
# 18. IP INTELLIGENCE
# ------------------------------------------------------------
IP_API_URL = os.getenv("IP_API_URL", "http://ip-api.com/json/{}")

# ------------------------------------------------------------
# 19. DEBUG
# ------------------------------------------------------------
DEBUG     = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

print("✅ CONFIG LOADED — PostgreSQL + Google Sheets + IP Intelligence")
print(f"🚀 Bot Mode : {BOT_MODE.upper()}")
print(f"👑 Owner ID : {OWNER_ID}")
print(f"📊 Sheet ID : {GOOGLE_SHEET_ID[:20]}..." if GOOGLE_SHEET_ID else "📊 Sheet   : DISABLED")
print(f"🔌 APIs     : {len(API_ENDPOINTS)} endpoints across {len(API_CATEGORIES)} categories")
