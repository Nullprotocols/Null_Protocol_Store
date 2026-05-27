# sheets.py - UPGRADED: Single "All Logs" tab + env-based Sheet ID

import json
import base64
import asyncio
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GSHEET_CREDS

logger = logging.getLogger(__name__)

# ── Global state ───────────────────────────────────────────────
gc        = None
_sheet    = None
_ws       = None          # Single "All Logs" worksheet

ALL_LOGS_TAB = "📋 All Logs"

HEADERS = [
    "Timestamp (UTC)",
    "API Type",
    "API Name",
    "API Key (masked)",
    "Input",
    "Client IP",
    "Country",
    "City",
    "ISP",
    "Response JSON",
]

# Column pixel widths (must match HEADERS order)
COL_WIDTHS = [160, 90, 180, 180, 160, 130, 100, 120, 200, 500]

# Colour palette
_DARK_BLUE  = {"red": 0.102, "green": 0.459, "blue": 0.910}  # #1a73e8
_WHITE      = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }
_LIGHT_BLUE = {"red": 0.910, "green": 0.940, "blue": 0.980}  # #e8f0fe


# ══════════════════════════════════════════════════════════════
def init_sheets() -> bool:
    """
    Connect to Google Sheets using GOOGLE_SHEET_ID env variable.
    Create / format the single "All Logs" tab.
    Returns True on success, False on failure.
    """
    global gc, _sheet, _ws

    if not GOOGLE_SHEET_ID:
        logger.warning("⚠️  GOOGLE_SHEET_ID not set — Sheets logging disabled.")
        return False
    if not GSHEET_CREDS:
        logger.warning("⚠️  GSHEET_CREDS not set — Sheets logging disabled.")
        return False

    try:
        creds_json  = json.loads(base64.b64decode(GSHEET_CREDS).decode("utf-8"))
        credentials = Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc     = gspread.authorize(credentials)
        _sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        logger.info(f"✅ Connected to Google Sheet: {_sheet.title}  (ID: {GOOGLE_SHEET_ID})")

        # Get or create "All Logs" worksheet
        try:
            _ws = _sheet.worksheet(ALL_LOGS_TAB)
            logger.info(f"📄 Tab found: {ALL_LOGS_TAB}")
        except gspread.exceptions.WorksheetNotFound:
            _ws = _sheet.add_worksheet(title=ALL_LOGS_TAB, rows=5000, cols=len(HEADERS))
            logger.info(f"📄 Created tab: {ALL_LOGS_TAB}")

        _apply_formatting(_ws)
        return True

    except Exception as e:
        logger.error(f"❌ Google Sheets init failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════
def _apply_formatting(ws: gspread.Worksheet) -> None:
    """Apply dark-blue header, freeze row, column widths, alternating rows."""
    num_cols = len(HEADERS)
    last_col = chr(ord('A') + num_cols - 1)   # e.g. 'J' for 10 cols

    try:
        # 1. Write headers (only if row 1 is empty)
        existing = ws.row_values(1)
        if not existing or existing[0] != HEADERS[0]:
            ws.update(values=[HEADERS], range_name="A1")

        # 2. Header row styling
        ws.format(f"A1:{last_col}1", {
            "backgroundColor": _DARK_BLUE,
            "textFormat": {
                "foregroundColor": _WHITE,
                "bold": True,
                "fontSize": 11,
                "fontFamily": "Roboto",
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        })

        # 3. Freeze header row
        ws.freeze(rows=1)

        # 4. Column widths via batchUpdate
        requests = [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": w},
                    "fields": "pixelSize",
                }
            }
            for i, w in enumerate(COL_WIDTHS)
        ]
        if requests:
            try:
                _sheet.batch_update({"requests": requests})
            except Exception as e:
                logger.warning(f"Column resize warning: {e}")

        # 5. Alternating row colours (gspread v6 compatible way)
        try:
            rule = {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": ws.id,
                            "startRowIndex": 1,
                            "endRowIndex": 5000,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": "=ISEVEN(ROW())"}],
                            },
                            "format": {"backgroundColor": _LIGHT_BLUE},
                        },
                    },
                    "index": 0,
                }
            }
            _sheet.batch_update({"requests": [rule]})
        except Exception as e:
            logger.warning(f"Conditional formatting warning (non-fatal): {e}")

        logger.info(f"🎨 Formatting applied to '{ALL_LOGS_TAB}'")

    except Exception as e:
        logger.error(f"❌ Formatting error: {e}")


# ══════════════════════════════════════════════════════════════
def log_api_call_sync(
    api_type: str,
    api_name: str,
    api_key: str,
    input_value: str,
    client_ip: str,
    ip_info: dict,
    response_data,
) -> None:
    """
    Synchronous log writer — runs in thread pool to avoid blocking async loop.
    Logs every API call to the single "All Logs" tab.
    """
    if not gc or not _sheet or not _ws:
        return

    try:
        now         = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        masked_key  = (api_key[:12] + "...") if len(api_key) > 12 else api_key
        country     = ip_info.get("country", "N/A") if ip_info else "N/A"
        city        = ip_info.get("city",    "N/A") if ip_info else "N/A"
        isp         = ip_info.get("isp",     "N/A") if ip_info else "N/A"
        resp_json   = json.dumps(response_data, ensure_ascii=False)

        row = [
            now,
            api_type.upper(),
            api_name,
            masked_key,
            input_value,
            client_ip,
            country,
            city,
            isp,
            resp_json,
        ]

        _ws.append_row(row, value_input_option="USER_ENTERED")

        # ── Auto-prune: keep max 5000 data rows ──────────────
        try:
            total = len(_ws.get_all_values())   # includes header
            if total > 5001:
                _ws.delete_rows(2, total - 5001)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Sheet log error: {e}")


# ══════════════════════════════════════════════════════════════
async def log_api_call(
    api_type: str,
    api_name: str,
    api_key: str,
    input_value: str,
    client_ip: str,
    ip_info: dict,
    response_data,
) -> None:
    """Async wrapper — fire-and-forget background logging."""
    try:
        await asyncio.to_thread(
            log_api_call_sync,
            api_type, api_name, api_key,
            input_value, client_ip, ip_info, response_data,
        )
    except Exception as e:
        logger.error(f"Async sheet log error: {e}")
