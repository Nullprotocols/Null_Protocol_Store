# sheets.py - GOOGLE SHEETS INTEGRATION (ALL APIs, DYNAMIC TABS, OPTIMIZED)

import json
import base64
import asyncio
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GSHEET_CREDS, API_ENDPOINTS

logger = logging.getLogger(__name__)

# Global gspread client and sheet
gc = None
sheet = None
worksheet_cache = {}

# Tab names for all possible API types (matching keys in API_ENDPOINTS)
TAB_NAMES = {
    "num": "📞 Phone Info",
    "tg": "💬 Telegram Info",
    "mobile": "📱 Mobile Alt",
    "aadhaar": "🆔 Aadhaar",
    "email": "✉️ Email Lookup",
    "gst": "💰 GST Verification",
    "telegram_alt": "💬 Telegram Alt",
    "ifsc": "🏦 IFSC Code",
    "rashan": "🍚 Ration Card",
    "upi": "💳 UPI Lookup",
    "upi2": "💳 UPI v2",
    "vehicle_reg": "🚗 Vehicle Reg",
    "vehicle_to_number": "🚙 Vehicle→Phone",
    "pan": "🪪 PAN Card",
    "fastag": "🚘 FASTag",
    "challan": "📜 Traffic Challan",
    "gas": "🔥 Gas Connection",
    "number_info_backup": "📞 Phone Backup",
    "vehicle_backup": "🚛 Vehicle Backup",
    "vi_sim_info": "📶 Vi SIM Info",
    "drive": "📁 Drive Lookup"
}

# Headers for each tab
HEADERS = [
    "Timestamp (UTC)",
    "API Key",
    "Input",
    "Client IP",
    "Country",
    "City",
    "ISP",
    "Response JSON"
]

# Column widths (approximate pixel count)
COL_WIDTHS = [160, 200, 150, 130, 100, 120, 200, 400]

# Colors (Google Sheets hex format without #)
DARK_BLUE = {"red": 0.102, "green": 0.459, "blue": 0.91}   # #1a73e8
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
LIGHT_BLUE = {"red": 0.91, "green": 0.94, "blue": 0.98}    # #e8f0fe


def init_sheets():
    """
    Initialize Google Sheets connection, create tabs for all APIs (if not exist),
    and apply formatting only to newly created ones.
    """
    global gc, sheet

    if not GSHEET_CREDS:
        logger.warning("❌ GSHEET_CREDS not set. Sheets logging disabled.")
        return False

    try:
        # Decode base64 credentials
        creds_json = json.loads(base64.b64decode(GSHEET_CREDS).decode("utf-8"))
        credentials = Credentials.from_service_account_info(creds_json, scopes=[
            "https://www.googleapis.com/auth/spreadsheets"
        ])

        gc = gspread.authorize(credentials)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        logger.info(f"✅ Connected to Google Sheet: {sheet.title}")

        # Ensure a tab exists for every API type defined in config
        for api_type in API_ENDPOINTS:
            tab_name = TAB_NAMES.get(api_type, f"📊 {api_type.upper()}")
            try:
                ws = sheet.worksheet(tab_name)
                logger.info(f"📄 Found existing tab: {tab_name}")
            except gspread.exceptions.WorksheetNotFound:
                ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(HEADERS))
                logger.info(f"📄 Created new tab: {tab_name}")
                _apply_formatting(ws, tab_name)

            worksheet_cache[api_type] = ws

        return True

    except Exception as e:
        logger.error(f"❌ Google Sheets init failed: {e}")
        return False


def _apply_formatting(ws, tab_name):
    """
    Apply attractive formatting to a NEW worksheet tab:
    - Dark blue header with white bold text
    - Frozen first row
    - Column auto-resize
    - Alternating row colors via conditional formatting
    Only called when the tab is first created.
    """
    num_cols = len(HEADERS)

    try:
        # 1. Set headers (only once)
        ws.update(values=[HEADERS], range_name="A1")

        # 2. Format header row
        ws.format("A1:H1", {
            "backgroundColor": DARK_BLUE,
            "textFormat": {
                "foregroundColor": WHITE,
                "bold": True,
                "fontSize": 11,
                "fontFamily": "Roboto"
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE"
        })

        # 3. Freeze first row
        ws.freeze(rows=1)

        # 4. Set column widths via batch update (one time)
        requests = []
        for i, width in enumerate(COL_WIDTHS):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize"
                }
            })

        if requests:
            try:
                sheet.batch_update({"requests": requests})
            except Exception as e:
                logger.warning(f"Column resize warning: {e}")

        # 5. Apply alternating row colors (conditional formatting)
        try:
            ws.add_conditional_formatting(
                "A2:H1000",   # apply to first 1000 rows (will expand automatically)
                {
                    "type": "CUSTOM_FORMULA",
                    "values": [{"userEnteredValue": "=ISEVEN(ROW())"}],
                    "format": {
                        "backgroundColor": LIGHT_BLUE
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Conditional formatting warning: {e}")

        logger.info(f"🎨 Formatting applied to new tab: {tab_name}")

    except Exception as e:
        logger.error(f"❌ Formatting error for {tab_name}: {e}")


def log_api_call_sync(api_type, api_key, input_value, client_ip, ip_info, response_data):
    """
    Synchronously log an API call to Google Sheet.
    This function is designed to be run in a thread (via asyncio.to_thread)
    to avoid blocking the async event loop.
    """
    if not gc or not sheet:
        return

    try:
        ws = worksheet_cache.get(api_type)
        if not ws:
            logger.warning(f"No worksheet found for {api_type}, attempting to create one...")
            # Fallback: create tab on the fly (shouldn't happen if init was successful)
            tab_name = TAB_NAMES.get(api_type, f"📊 {api_type.upper()}")
            try:
                ws = sheet.worksheet(tab_name)
            except gspread.exceptions.WorksheetNotFound:
                ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(HEADERS))
                _apply_formatting(ws, tab_name)
            worksheet_cache[api_type] = ws

        # Prepare row data
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        masked_key = api_key[:12] + "..." if len(api_key) > 12 else api_key
        country = ip_info.get("country", "N/A") if ip_info else "N/A"
        city = ip_info.get("city", "N/A") if ip_info else "N/A"
        isp = ip_info.get("isp", "N/A") if ip_info else "N/A"
        response_json = json.dumps(response_data, ensure_ascii=False)

        row = [now, masked_key, input_value, client_ip, country, city, isp, response_json]

        # Append row
        ws.append_row(row, value_input_option="USER_ENTERED")

        # Auto-clean: keep max 5000 rows (delete oldest 100 if exceeded)
        # Use row_count instead of get_all_values for speed
        try:
            total_rows = ws.row_count
            if total_rows > 5000:
                ws.delete_rows(2, 100)  # Delete rows 2-101 (header untouched)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Sheet logging error: {e}")


async def log_api_call(api_type, api_key, input_value, client_ip, ip_info, response_data):
    """
    Async wrapper that runs the sync log function in a thread pool.
    This is called from the Quart route as a background task.
    """
    try:
        await asyncio.to_thread(
            log_api_call_sync,
            api_type, api_key, input_value, client_ip, ip_info, response_data
        )
    except Exception as e:
        logger.error(f"Async sheet logging error: {e}")
