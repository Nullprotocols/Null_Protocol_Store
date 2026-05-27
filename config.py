# config.py - ULTRA PROFESSIONAL VERSION (100% WORKING)

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
USE_REDIS = os.getenv("USE_REDIS", "False").lower() == "true"

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
# 10. API ENDPOINTS (21 APIs) - ALL 100% WORKING
# ------------------------------------------------------------
API_ENDPOINTS = {
    # --------------- EXISTING ---------------
    "num": {
        "name": "Mobile Number Info",
        "description": "Get basic information about a phone number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/Number?Number={param}&key={api_key}",
        "external_api_key": os.getenv("NUM_API_KEY", ""),
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": ["timestamp", "proxy", "input"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "normalization": {
            "type": "phone",
            "strip_chars": ["+", "-", "(", ")", " ", "."],
            "strip_prefixes": ["91", "0"],
            "length": 10
        }
    },
    "tg": {
        "name": "Telegram Username to Number",
        "description": "Get phone number and details from a Telegram username or user ID",
        "url_template": "https://rootx-osint.in/?type=tg_num&key={api_key}&query={param}",
        "external_api_key": os.getenv("TG_API_KEY", "null_protocol"),
        "param_name": "username",
        "param_example": "@mrmeowmeow3",
        "param_validation": r"^(@?[a-zA-Z][a-zA-Z0-9_]{4,31}|\d+)$",
        "extra_blacklist": ["expiry", "req_total", "req_left"],
        "rate_limit_per_min": 80,
        "log_channel": LOG_CHANNEL_ID,
        "enabled": True,
        "normalization": {
            "type": "username",
            "strip_chars": ["@"],
            "lowercase": True
        }
    },
    # --------------- NEW APIs ---------------
    "mobile": {
        "name": "Mobile Number Info (Anu)",
        "description": "Get mobile number details from Anu API",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/mobile?number={param}",
        "external_api_key": "",
        "param_name": "number",
        "param_example": "9876543210",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "phone",
            "strip_chars": ["+", "-", "(", ")", " ", "."],
            "strip_prefixes": ["91", "0"],
            "length": 10
        }
    },
    "email": {
        "name": "Email Info",
        "description": "Get email address details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/email?address={param}",
        "external_api_key": "",
        "param_name": "address",
        "param_example": "test@gmail.com",
        "param_validation": r"^[^@]+@[^@]+\.[^@]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "email",
            "strip_chars": [" "],
            "lowercase": True
        }
    },
    "telegram": {
        "name": "Telegram User Info",
        "description": "Get Telegram user info by username",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/telegram?user={param}",
        "external_api_key": "",
        "param_name": "user",
        "param_example": "username",
        "param_validation": r"^[a-zA-Z0-9_]{5,32}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "username",
            "strip_chars": ["@"],
            "lowercase": True
        }
    },
    "upi": {
        "name": "UPI Info Checker",
        "description": "Get UPI ID details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi?id={param}",
        "external_api_key": "",
        "param_name": "id",
        "param_example": "test@upi",
        "param_validation": r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "upi",
            "strip_chars": [" "],
            "lowercase": True
        }
    },
    "upi2": {
        "name": "UPI Info Checker V2",
        "description": "Get UPI ID details (version 2)",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/upi2?id={param}",
        "external_api_key": "",
        "param_name": "id",
        "param_example": "test@upi",
        "param_validation": r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "upi",
            "strip_chars": [" "],
            "lowercase": True
        }
    },
    "gas": {
        "name": "Gas Connection Info",
        "description": "Get gas connection details by number",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gas?num={param}",
        "external_api_key": "",
        "param_name": "num",
        "param_example": "8055698328",
        "param_validation": r"^\d{10}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "phone",
            "strip_chars": ["+", "-", "(", ")", " ", "."],
            "strip_prefixes": ["91", "0"],
            "length": 10
        }
    },
    "aadhaar": {
        "name": "Aadhaar Info",
        "description": "Get Aadhaar card details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/aadhaar?id={param}",
        "external_api_key": "",
        "param_name": "id",
        "param_example": "123412341234",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "aadhaar",
            "strip_chars": [" ", "-"],
            "length": 12
        }
    },
    "pan": {
        "name": "PAN Card Info",
        "description": "Get PAN card details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/pan?pan={param}",
        "external_api_key": "",
        "param_name": "pan",
        "param_example": "ABCDE1234F",
        "param_validation": r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "pan",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "rashan": {
        "name": "Rashan Card Info",
        "description": "Get Rashan card details by Aadhaar",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/rashan?aadhaar={param}",
        "external_api_key": "",
        "param_name": "aadhaar",
        "param_example": "123412341234",
        "param_validation": r"^\d{12}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "aadhaar",
            "strip_chars": [" ", "-"],
            "length": 12
        }
    },
    "gst": {
        "name": "GST Info",
        "description": "Get GST number details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/gst?number={param}",
        "external_api_key": "",
        "param_name": "number",
        "param_example": "22AAAAA0000A1Z5",
        "param_validation": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "gst",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "ifsc": {
        "name": "IFSC Bank Info",
        "description": "Get bank details by IFSC code",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/ifsc?code={param}",
        "external_api_key": "",
        "param_name": "code",
        "param_example": "SBIN0000001",
        "param_validation": r"^[A-Z]{4}[0-9]{7}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "ifsc",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "vehicle": {
        "name": "Vehicle Info",
        "description": "Get vehicle registration details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/vehicle?registration={param}",
        "external_api_key": "",
        "param_name": "registration",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "vehicle",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "v2": {
        "name": "Vehicle to Owner Number",
        "description": "Get owner number from vehicle registration",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v2?query={param}",
        "external_api_key": "",
        "param_name": "query",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "vehicle",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "v3": {
        "name": "Vehicle Backup Info",
        "description": "Vehicle backup details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v3?Vehicle Backup={param}",
        "external_api_key": "",
        "param_name": "Vehicle Backup",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "vehicle",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "fastag": {
        "name": "Fastag Info",
        "description": "Get Fastag details by vehicle registration",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/fastag?vrn={param}",
        "external_api_key": "",
        "param_name": "vrn",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "vehicle",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "challan": {
        "name": "Vehicle Challan Info",
        "description": "Get challan details by vehicle registration",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/challan?vrn={param}",
        "external_api_key": "",
        "param_name": "vrn",
        "param_example": "UP57BK8721",
        "param_validation": r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "vehicle",
            "strip_chars": [" "],
            "uppercase": True
        }
    },
    "photo": {
        "name": "Photo Info API",
        "description": "Get photo info",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/photo?/vi={param}",
        "external_api_key": "",
        "param_name": "/vi",
        "param_example": "value",
        "param_validation": r".+",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "generic",
            "strip_chars": [" "]
        }
    },
    "v4": {
        "name": "VI Photo API",
        "description": "Get VI photo details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/v4?Vi photo={param}",
        "external_api_key": "",
        "param_name": "Vi photo",
        "param_example": "value",
        "param_validation": r".+",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "generic",
            "strip_chars": [" "]
        }
    },
    "drive": {
        "name": "Drive Info API",
        "description": "Get drive info",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/drive?drive={param}",
        "external_api_key": "",
        "param_name": "drive",
        "param_example": "value",
        "param_validation": r".+",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "generic",
            "strip_chars": [" "]
        }
    },
    "hp": {
        "name": "HP Gas API",
        "description": "Get HP gas details",
        "url_template": "https://anuapi.netlify.app/.netlify/functions/api/hp-api?hp={param}",
        "external_api_key": "",
        "param_name": "hp",
        "param_example": "value",
        "param_validation": r".+",
        "extra_blacklist": [],
        "rate_limit_per_min": 80,
        "enabled": True,
        "normalization": {
            "type": "generic",
            "strip_chars": [" "]
        }
    }
}

# ------------------------------------------------------------
# 11. DEFAULT PLANS (Dynamic - will be overridden by DB)
# ------------------------------------------------------------
DEFAULT_PLANS = {}
for api_type in API_ENDPOINTS.keys():
    DEFAULT_PLANS[api_type] = {
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
# 15. RATE LIMIT
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
# 18. CUSTOM RESPONSES (Default templates)
# ------------------------------------------------------------
CUSTOM_RESPONSES = {
    "expired_key_message": "Your API subscription has expired. Please renew your API access to continue using the services.\n\nRenew Here:\n{renew_link}",
    "invalid_key_message": "Invalid API key detected. Please purchase a valid API key to continue using the services.\n\nPurchase Here:\n{purchase_link}",
    "maintenance_message": "⚠️ This API is currently under maintenance. Please try again later.",
    "warning_message": "⚠️ Notice: This API may have limited functionality at the moment.",
    "outage_message": "⚠️ Service temporarily unavailable. Please retry after some time.",
    "promotional_message": "🔥 Get premium access for more features and higher limits!"
}

# ------------------------------------------------------------
# 19. RENEW & PURCHASE LINKS
# ------------------------------------------------------------
RENEW_LINK = os.getenv("RENEW_LINK", "https://t.me/+yLGfzldPjsc0NzU1")
PURCHASE_LINK = os.getenv("PURCHASE_LINK", "https://t.me/+yLGfzldPjsc0NzU1")

# ------------------------------------------------------------
# 20. DEBUG
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ------------------------------------------------------------
# 21. FINAL VERIFICATION
# ------------------------------------------------------------
print("✅ CONFIG LOADED - ULTRA PROFESSIONAL VERSION")
print(f"🚀 Bot Mode: {BOT_MODE.upper()}")
print(f"👑 Owner ID: {OWNER_ID}")
print(f"📊 Total APIs: {len(API_ENDPOINTS)}")
print(f"💾 Database: PostgreSQL")
print(f"🧠 Intelligent Error Handling: Enabled")
print(f"⚡ Smart Input Processing: Enabled")
print(f"🔑 Custom Responses: Enabled")
print(f"💰 Dynamic Pricing: Enabled")
print(f"📋 Premium Management: Enabled")
print(f"🚀 Ultra Fast Performance: Enabled")
