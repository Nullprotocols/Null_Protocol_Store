# config.py - FINAL PRODUCTION VERSION (ALL 20+ APIs, NORMALIZATION, CUSTOM MESSAGES)

import os
import re

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
    {"id": -1003090922367, "link": "https://t.me/all_data_here", "name": "All Data Here"},
    {"id": -1003698567122, "link": "https://t.me/osint_lookup", "name": "OSINT Lookup"},
    {"id": -1003672015073, "link": "https://t.me/legend_chats_osint", "name": "LEGEND CHATS"}
]

# ------------------------------------------------------------
# 9. LOG CHANNEL
# ------------------------------------------------------------
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003624886596"))

# ------------------------------------------------------------
# 10. API ENDPOINTS (FULL PROFESSIONAL REGISTRY)
# ------------------------------------------------------------

# ====================== INPUT NORMALIZATION FUNCTIONS ======================
def normalize_phone_10_digit(value: str) -> str:
    """Strip all non-digits, take last 10 digits. For 10-digit phone APIs."""
    digits = re.sub(r'\D', '', value)
    return digits[-10:] if len(digits) >= 10 else digits

def normalize_email(value: str) -> str:
    """Lowercase and trim."""
    return value.strip().lower()

def normalize_upper_alphanum(value: str) -> str:
    """Uppercase, remove spaces, keep only alphanumeric."""
    return re.sub(r'\s+', '', value).upper()

def normalize_vehicle(value: str) -> str:
    """Uppercase, remove spaces."""
    return re.sub(r'\s+', '', value).upper()

def normalize_ifsc(value: str) -> str:
    """Uppercase, remove spaces."""
    return re.sub(r'\s+', '', value).upper()

def normalize_upi(value: str) -> str:
    """Trim and lowercase."""
    return value.strip().lower()

def normalize_username(value: str) -> str:
    """Strip and remove leading @."""
    return value.strip().lstrip('@')

def normalize_aadhaar(value: str) -> str:
    """Remove spaces."""
    return re.sub(r'\s', '', value)

# ====================== ENDPOINTS ======================
API_ENDPOINTS = {
    # --------------------------------------------------------
    # Existing APIs (improved)
    # --------------------------------------------------------
    "num": {
        "name": "📞 Phone Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("NUM_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": ["timestamp", "proxy", "input"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Your key for Phone Number Info has expired. Renew now: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid key! Buy a new one for Phone Number Info: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "tg": {
        "name": "💬 Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username or user ID",
        "url_template": "https://rootx-osint.in/?type=tg_num&key={api_key}&query={param}",
        "external_api_key": os.getenv("TG_API_KEY", "null_protocol"),
        "param_name": "username",
        "param_example": "@mrmeowmeow3 or 123456789",
        "param_validation": r"^(@?[a-zA-Z][a-zA-Z0-9_]{4,31}|\d+)$",
        "preprocess": normalize_username,
        "extra_blacklist": ["expiry", "req_total", "req_left"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "TG API key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid TG API key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },

    # --------------------------------------------------------
    # NEW APIs (from your list)
    # --------------------------------------------------------
    "mobile": {
        "name": "📱 Mobile Number Info (Alt)",
        "description": "Details of a mobile number (alternate)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/mobile?number={param}&key={api_key}",
        "external_api_key": os.getenv("MOBILE_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Mobile info key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid key for Mobile Info. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "aadhaar": {
        "name": "🆔 Aadhaar Details",
        "description": "⚠️ Sensitive. Use legally.",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/aadhaar?id={param}&key={api_key}",
        "external_api_key": os.getenv("AADHAAR_API_KEY", ""),
        "param_name": "id",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "preprocess": normalize_aadhaar,
        "extra_blacklist": [],
        "rate_limit_per_min": 20,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": False,  # disabled by default (legal)
        "expired_message": "Aadhaar key expired. Contact admin.",
        "invalid_message": "Invalid Aadhaar key. Contact admin."
    },
    "email": {
        "name": "✉️ Email Lookup",
        "description": "Check info for an email address",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/email?address={param}&key={api_key}",
        "external_api_key": os.getenv("EMAIL_API_KEY", ""),
        "param_name": "address",
        "param_example": "test@example.com",
        "param_validation": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        "preprocess": normalize_email,
        "extra_blacklist": [],
        "rate_limit_per_min": 50,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Email lookup key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid key for Email. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "gst": {
        "name": "💰 GST Verification",
        "description": "Verify GST number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gst?number={param}&key={api_key}",
        "external_api_key": os.getenv("GST_API_KEY", ""),
        "param_name": "number",
        "param_example": "27ABCDE1234F1Z5",
        "param_validation": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
        "preprocess": normalize_upper_alphanum,
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "GST key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid GST key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "telegram_alt": {
        "name": "💬 Telegram Lookup (Alt)",
        "description": "Alternate Telegram username to number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/telegram?user={param}&key={api_key}",
        "external_api_key": os.getenv("TELEGRAM_ALT_API_KEY", ""),
        "param_name": "user",
        "param_example": "username",
        "param_validation": r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$",
        "preprocess": normalize_username,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Telegram Alt key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Telegram Alt key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "ifsc": {
        "name": "🏦 IFSC Code Lookup",
        "description": "Bank details from IFSC",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/ifsc?code={param}&key={api_key}",
        "external_api_key": os.getenv("IFSC_API_KEY", ""),
        "param_name": "code",
        "param_example": "SBIN0001234",
        "param_validation": r"^[A-Z]{4}0[A-Z0-9]{6}$",
        "preprocess": normalize_ifsc,
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "IFSC key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid IFSC key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "rashan": {
        "name": "🍚 Ration Card (Aadhaar linked)",
        "description": "Ration details via Aadhaar",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/rashan?aadhaar={param}&key={api_key}",
        "external_api_key": os.getenv("RASHAN_API_KEY", ""),
        "param_name": "aadhaar",
        "param_example": "123456789012",
        "param_validation": r"^\d{12}$",
        "preprocess": normalize_aadhaar,
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": False,
        "expired_message": "Ration card key expired. Contact admin.",
        "invalid_message": "Invalid ration card key. Contact admin."
    },
    "upi": {
        "name": "💳 UPI ID Lookup",
        "description": "Check UPI ID details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi?id={param}&key={api_key}",
        "external_api_key": os.getenv("UPI_API_KEY", ""),
        "param_name": "id",
        "param_example": "user@upi",
        "param_validation": r"^[\w\.\-]+@[\w\.\-]+$",
        "preprocess": normalize_upi,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "UPI key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid UPI key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "upi2": {
        "name": "💳 UPI ID Lookup (v2)",
        "description": "Alternate UPI lookup",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi2?id={param}&key={api_key}",
        "external_api_key": os.getenv("UPI2_API_KEY", ""),
        "param_name": "id",
        "param_example": "user@upi",
        "param_validation": r"^[\w\.\-]+@[\w\.\-]+$",
        "preprocess": normalize_upi,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "UPI v2 key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid UPI v2 key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "vehicle_reg": {
        "name": "🚗 Vehicle Registration",
        "description": "Vehicle details by registration number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/vehicle?registration={param}&key={api_key}",
        "external_api_key": os.getenv("VEHICLE_REG_API_KEY", ""),
        "param_name": "registration",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$",
        "preprocess": normalize_vehicle,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Vehicle Reg key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid vehicle reg key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "vehicle_to_number": {
        "name": "🚙 Vehicle to Phone Number",
        "description": "Find mobile number linked to vehicle",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v2?query={param}&key={api_key}",
        "external_api_key": os.getenv("VEHICLE_TO_NUMBER_API_KEY", ""),
        "param_name": "query",
        "param_example": "up57bk8721",
        "param_validation": r"^[A-Z0-9]+$",
        "preprocess": normalize_vehicle,
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Vehicle-to-Number key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Vehicle-to-Number key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "pan": {
        "name": "🪪 PAN Verification",
        "description": "PAN card details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/pan?pan={param}&key={api_key}",
        "external_api_key": os.getenv("PAN_API_KEY", ""),
        "param_name": "pan",
        "param_example": "ABCDE1234F",
        "param_validation": r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
        "preprocess": normalize_upper_alphanum,
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": False,  # legal caution
        "expired_message": "PAN key expired. Contact admin.",
        "invalid_message": "Invalid PAN key. Contact admin."
    },
    "fastag": {
        "name": "🚘 FASTag Info",
        "description": "FASTag details via vehicle number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/fastag?vrn={param}&key={api_key}",
        "external_api_key": os.getenv("FASTAG_API_KEY", ""),
        "param_name": "vrn",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z0-9]+$",
        "preprocess": normalize_vehicle,
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "FASTag key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid FASTag key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "challan": {
        "name": "📜 Traffic Challan",
        "description": "Traffic challan details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/challan?vrn={param}&key={api_key}",
        "external_api_key": os.getenv("CHALLAN_API_KEY", ""),
        "param_name": "vrn",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z0-9]+$",
        "preprocess": normalize_vehicle,
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Challan key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid challan key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "gas": {
        "name": "🔥 Gas Connection",
        "description": "Gas connection info by phone number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gas?num={param}&key={api_key}",
        "external_api_key": os.getenv("GAS_API_KEY", ""),
        "param_name": "num",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Gas key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid gas key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "number_info_backup": {
        "name": "📞 Phone Info (Backup)",
        "description": "Alternate phone number info (same as Number endpoint)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("NUMBER_BACKUP_API_KEY", ""),
        "param_name": "Number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Phone backup key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Phone backup key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "vehicle_backup": {
        "name": "🚛 Vehicle Backup API",
        "description": "Alternative vehicle lookup (v3)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v3?Vehicle%20Backup={param}&key={api_key}",
        "external_api_key": os.getenv("VEHICLE_BACKUP_API_KEY", ""),
        "param_name": "Vehicle Backup",
        "param_example": "UP32AB1234",
        "param_validation": r"^[A-Z0-9]+$",
        "preprocess": normalize_vehicle,
        "extra_blacklist": [],
        "rate_limit_per_min": 60,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Vehicle Backup key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Vehicle Backup key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "vi_sim_photo": {
        "name": "📷 Vi SIM Info & Photo",
        "description": "Vi SIM details with photo (fixed URL)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/photo?vi={param}&key={api_key}",
        "external_api_key": os.getenv("VI_SIM_PHOTO_API_KEY", ""),
        "param_name": "vi",
        "param_example": "1234567890",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Vi SIM photo key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Vi SIM photo key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "vi_sim_info": {
        "name": "📶 Vi SIM Info",
        "description": "Vi SIM card information (v4)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v4?Vi%20photo={param}&key={api_key}",
        "external_api_key": os.getenv("VI_API_KEY", ""),
        "param_name": "Vi photo",
        "param_example": "1234567890",
        "param_validation": r"^\d{10}$",
        "preprocess": normalize_phone_10_digit,
        "extra_blacklist": [],
        "rate_limit_per_min": 70,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "expired_message": "Vi SIM key expired. Renew: https://t.me/+yLGfzldPjsc0NzU1",
        "invalid_message": "Invalid Vi SIM key. Buy: https://t.me/+yLGfzldPjsc0NzU1"
    },
    "drive": {
        "name": "📁 Drive Lookup",
        "description": "Google Drive or file lookup (to be defined)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/drive?drive={param}&key={api_key}",
        "external_api_key": os.getenv("DRIVE_API_KEY", ""),
        "param_name": "drive",
        "param_example": "???",
        "param_validation": r"^.+$",
        "preprocess": lambda x: x.strip(),
        "extra_blacklist": [],
        "rate_limit_per_min": 30,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": False,  # incomplete, enable after clarity
        "expired_message": "Drive key expired. Contact admin.",
        "invalid_message": "Invalid Drive key. Contact admin."
    }
}

# ------------------------------------------------------------
# 11. PLANS
# ------------------------------------------------------------
DEFAULT_PLANS = {
    "num": {"weekly": {"credits": 15, "days": 7}, "monthly": {"credits": 30, "days": 30}},
    "tg":  {"weekly": {"credits": 15, "days": 7}, "monthly": {"credits": 30, "days": 30}}
    # Other API plans will be generated dynamically in database.py
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
# 15. RATE LIMIT
# ------------------------------------------------------------
DEFAULT_RATE_LIMIT_PER_MIN = int(os.getenv("DEFAULT_RATE_LIMIT", "80"))

# ------------------------------------------------------------
# 16. BACKUP
# ------------------------------------------------------------
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", str(OWNER_ID)))

# ------------------------------------------------------------
# 17. GOOGLE SHEETS CONFIGURATION
# ------------------------------------------------------------
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1fn5yyUZmOAbX6bBafL3L4lrHxHLuaiBpaq4JoqxHOhE")
GSHEET_CREDS = os.getenv("GSHEET_CREDS", "")  # base64 encoded service account JSON

# ------------------------------------------------------------
# 18. IP INTELLIGENCE CONFIGURATION
# ------------------------------------------------------------
IP_API_URL = os.getenv("IP_API_URL", "http://ip-api.com/json/{}")  # {} replaced by IP

# ------------------------------------------------------------
# 19. DEBUG
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

print("✅ CONFIG LOADED - POSTGRESQL + GOOGLE SHEETS + IP INTELLIGENCE + 20+ APIs")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"📊 Google Sheet ID: {GOOGLE_SHEET_ID[:20]}...")
print(f"💾 Database: PostgreSQL")
print(f"📡 APIs Loaded: {len(API_ENDPOINTS)}")
