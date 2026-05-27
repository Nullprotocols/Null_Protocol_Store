# config.py - FINAL PRODUCTION VERSION (ALL APIs + REDIS + IP INTELLIGENCE + POSTGRESQL LOGGING)

import os

# ------------------------------------------------------------
# 1. TELEGRAM BOT
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN missing!")

OWNER_ID = int(os.getenv("OWNER_ID", "8104850843"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    raise ValueError("❌ WEBHOOK_SECRET missing! Set a strong secret token in env vars.")

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
# 4. CACHE & RATE LIMITING (Redis)
# ------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", None)   # Upstash or any Redis instance URL
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# ------------------------------------------------------------
# 5. AUTO-PING (Keep Render alive)
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
# 7. GLOBAL BLACKLIST (fields removed from API responses)
# ------------------------------------------------------------
GLOBAL_BLACKLIST = [
    "copyright", "signature", "credit", "source",
    "developer", "powered_by", "support", "website"
]

# ------------------------------------------------------------
# 8. FORCE JOIN CHANNELS (env-variable friendly)
# ------------------------------------------------------------
FORCE_JOIN_CHANNELS = [
    {
        "id": int(os.getenv("FJ_CH1_ID", "-1003090922367")),
        "link": os.getenv("FJ_CH1_LINK", "https://t.me/all_data_here"),
        "name": "All Data Here"
    },
    {
        "id": int(os.getenv("FJ_CH2_ID", "-1003698567122")),
        "link": os.getenv("FJ_CH2_LINK", "https://t.me/osint_lookup"),
        "name": "OSINT Lookup"
    },
    {
        "id": int(os.getenv("FJ_CH3_ID", "-1003672015073")),
        "link": os.getenv("FJ_CH3_LINK", "https://t.me/legend_chats_osint"),
        "name": "LEGEND CHATS"
    }
]

# ------------------------------------------------------------
# 9. LOG CHANNEL
# ------------------------------------------------------------
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003624886596"))

# ------------------------------------------------------------
# 10. ALL API ENDPOINTS (20+ APIs integrated)
# ------------------------------------------------------------
API_ENDPOINTS = {
    # ----- EXISTING APIs -----
    "num": {
        "name": "Phone Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("NUM_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp", "proxy", "input"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    },
    "tg": {
        "name": "Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username or user ID",
        "url_template": "https://rootx-osint.in/?type=tg_num&key={api_key}&query={param}",
        "external_api_key": os.getenv("TG_API_KEY", "null_protocol"),
        "param_name": "username",
        "param_example": "@mrmeowmeow3 ya 123456789",
        "param_validation": r"^(@?[a-zA-Z][a-zA-Z0-9_]{4,31}|\d+)$",
        "extra_blacklist": ["expiry", "req_total", "req_left"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True
    },

    # ----- NEW APIs (from your list) -----
    "mobile": {
        "name": "Mobile Number Info",
        "description": "Get mobile number details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/mobile?number={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "enabled": True
    },
    "aadhaar": {
        "name": "Aadhaar Info",
        "description": "Get Aadhaar details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/aadhaar?id={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "aadhaar",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "email": {
        "name": "Email Lookup",
        "description": "Get email address info",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/email?address={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "email",
        "param_example": "test@example.com",
        "param_validation": r"^[\w\.-]+@[\w\.-]+\.\w{2,}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "gst": {
        "name": "GST Verification",
        "description": "GST number details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gst?number={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "gstin",
        "param_example": "27ABCDE1234F1Z5",
        "param_validation": r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "telegram": {
        "name": "Telegram Lookup",
        "description": "Telegram username info",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/telegram?user={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "username",
        "param_example": "username",
        "param_validation": r"^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "enabled": True
    },
    "ifsc": {
        "name": "IFSC Code Lookup",
        "description": "Bank details from IFSC",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/ifsc?code={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "ifsc",
        "param_example": "SBIN0001234",
        "param_validation": r"^[A-Z]{4}0[A-Z0-9]{6}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "enabled": True
    },
    "rashan": {
        "name": "Ration Card Info",
        "description": "Ration card details via Aadhaar",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/rashan?aadhaar={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "aadhaar",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "upi": {
        "name": "UPI Lookup",
        "description": "Get UPI ID details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi?id={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "upi_id",
        "param_example": "user@upi",
        "param_validation": r"^[\w\.\-]+@[\w]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "enabled": True
    },
    "upi2": {
        "name": "UPI Lookup v2",
        "description": "Alternative UPI details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi2?id={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "upi_id",
        "param_example": "user@upi",
        "param_validation": r"^[\w\.\-]+@[\w]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "enabled": True
    },
    "vehicle": {
        "name": "Vehicle Registration",
        "description": "Vehicle RC details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/vehicle?registration={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "reg_no",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "vehicle2": {
        "name": "Vehicle to Number",
        "description": "Vehicle registration alternative lookup",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v2?query={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "reg_no",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "pan": {
        "name": "PAN Verification",
        "description": "PAN card details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/pan?pan={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "pan",
        "param_example": "ABCDE1234F",
        "param_validation": r"^[A-Z]{5}\d{4}[A-Z]$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "fastag": {
        "name": "FASTag Info",
        "description": "FASTag vehicle details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/fastag?vrn={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "reg_no",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "challan": {
        "name": "Challan Lookup",
        "description": "Traffic challan details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/challan?vrn={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "reg_no",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "gas": {
        "name": "Gas Cylinder Info",
        "description": "Gas connection details by mobile",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gas?num={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "phone_number": {
        "name": "Phone Number Info (v2)",
        "description": "Alternate phone number details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True
    },
    "vehicle3": {
        "name": "Vehicle Backup",
        "description": "Vehicle RC backup lookup",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v3?Vehicle%20Backup={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "reg_no",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "vi_photo": {
        "name": "Vi SIM Info & Photo",
        "description": "Vi SIM details with photo",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/photo?/vi={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "number",
        "param_example": "1234567890",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 20,
        "enabled": True
    },
    "vi_sim": {
        "name": "Vi SIM Info",
        "description": "Vi SIM info without photo",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v4?Vi%20photo={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "number",
        "param_example": "1234567890",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    },
    "drive": {
        "name": "Google Drive Lookup",
        "description": "Get info from Google Drive link/file ID",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/drive?drive={param}&key={api_key}",
        "external_api_key": os.getenv("ANU_API_KEY", ""),
        "param_name": "drive_link",
        "param_example": "https://drive.google.com/file/d/XXXX/view",
        "param_validation": r"^.+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "enabled": True
    }
}

# ------------------------------------------------------------
# 11. PLANS (Auto-generated for all APIs)
# ------------------------------------------------------------
DEFAULT_PLANS = {}
for api in API_ENDPOINTS:
    DEFAULT_PLANS[api] = {
        "weekly": {"credits": 15, "days": 7},
        "monthly": {"credits": 30, "days": 30}
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
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@Nullprotocol_x")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Nullprotocol_x")

# ------------------------------------------------------------
# 15. DEFAULT RATE LIMIT
# ------------------------------------------------------------
DEFAULT_RATE_LIMIT_PER_MIN = int(os.getenv("DEFAULT_RATE_LIMIT", "80"))

# ------------------------------------------------------------
# 16. BACKUP
# ------------------------------------------------------------
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", str(OWNER_ID)))

# ------------------------------------------------------------
# 17. IP INTELLIGENCE
# ------------------------------------------------------------
IP_API_URL = os.getenv("IP_API_URL", "http://ip-api.com/json/{}")

# ------------------------------------------------------------
# 18. CUSTOM ERROR RESPONSES (can be overridden per API via admin panel)
# ------------------------------------------------------------
DEFAULT_ERROR_RESPONSES = {
    "expired_key": "⚠️ Your API subscription has expired.\nPlease renew your API access to continue using the services.\n\nSupport & Renewal:\nhttps://t.me/+yLGfzldPjsc0NzU1",
    "invalid_key": "❌ Invalid API key detected.\nPlease purchase a valid API key to access the services.\n\nPurchase Here:\nhttps://t.me/+yLGfzldPjsc0NzU1",
    "no_subscription": "🔒 You don't have an active subscription for this API.\nPlease buy a plan from /buy.",
    "rate_limit": "⏳ Too many requests. Please wait a moment and try again.",
    "upstream_error": "⚙️ Service temporarily unavailable. Please try again in a few minutes.",
    "invalid_input": "🚫 Invalid input format. Please check the example and try again."
}

# ------------------------------------------------------------
# 19. DEBUG
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

print("✅ CONFIG LOADED - ALL APIs + REDIS + IP INTELLIGENCE + POSTGRESQL LOGGING")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"💾 Database: PostgreSQL + Redis {'(enabled)' if REDIS_URL else '(disabled)'}")
