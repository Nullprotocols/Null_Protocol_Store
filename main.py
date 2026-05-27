# main.py - ULTRA PROFESSIONAL VERSION (100% WORKING)

import json
import asyncio
import secrets
import time
import re
import aiohttp
import logging
import os
from datetime import datetime, timedelta, timezone
from quart import Quart, request, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import *
from database import *
import database

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)
cache: dict = {}
http_session: aiohttp.ClientSession = None

# PTB application
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ====================== INTELLIGENT ERROR DECODER ======================
ERROR_MESSAGES = {
    "Service temporarily unavailable": "⚠️ Server temporary issue me hai, please thodi der baad try karein.",
    "Upstream error: 502": "❌ Requested data currently available nahi hai.",
    "Upstream error: 503": "⚠️ Service temporarily unavailable, please retry later.",
    "Upstream error: 504": "⚠️ Server response me delay ho raha hai, please thodi der baad try karein.",
    "Data not found": "❌ Requested data currently available nahi hai.",
    "Not found": "❌ Requested data currently available nahi hai.",
    "Invalid input": "❌ Entered details invalid hain, kindly correct input provide karein.",
    "Invalid parameter": "❌ Entered details invalid hain, kindly correct input provide karein.",
    "Bad request": "❌ Entered details invalid hain, kindly correct input provide karein.",
    "Rate limit exceeded": "⚠️ Too many requests. Please wait and try again.",
    "404": "❌ Requested endpoint not found.",
    "500": "⚠️ Internal server error. Please try again later.",
    "Connection refused": "⚠️ Connection failed. Please check your network and try again.",
    "Timeout": "⚠️ Request timeout. Please try again.",
    "EOF": "⚠️ Connection terminated unexpectedly. Please retry.",
}

def decode_error(error_text):
    """Convert technical error to user-friendly message"""
    if not error_text:
        return "⚠️ An error occurred. Please try again later."
    
    # If it's a 502 from the upstream API, treat as data not found
    if "502" in error_text or "Upstream error: 502" in error_text:
        return "❌ Requested data currently available nahi hai."
    
    for tech, friendly in ERROR_MESSAGES.items():
        if tech.lower() in error_text.lower():
            return friendly
    return f"⚠️ {error_text}"

# ====================== SMART INPUT NORMALIZATION ======================
def normalize_input(param_value, normalization_config):
    """Normalize input based on API-specific rules"""
    if not normalization_config or not param_value:
        return param_value
    
    normalized = str(param_value)
    norm_type = normalization_config.get("type", "generic")
    
    # Common strip chars
    strip_chars = normalization_config.get("strip_chars", [])
    for ch in strip_chars:
        normalized = normalized.replace(ch, "")
    
    # Phone number normalization
    if norm_type == "phone":
        normalized = re.sub(r'\D', '', normalized)
        strip_prefixes = normalization_config.get("strip_prefixes", [])
        for prefix in strip_prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        length = normalization_config.get("length", 10)
        if len(normalized) > length:
            normalized = normalized[-length:]
    
    # Username normalization
    elif norm_type == "username":
        if normalization_config.get("lowercase", False):
            normalized = normalized.lower()
        if normalized.startswith("@"):
            normalized = normalized[1:]
    
    # Email normalization
    elif norm_type == "email":
        if normalization_config.get("lowercase", False):
            normalized = normalized.lower()
    
    # UPI normalization
    elif norm_type == "upi":
        if normalization_config.get("lowercase", False):
            normalized = normalized.lower()
    
    # Aadhaar normalization
    elif norm_type == "aadhaar":
        normalized = re.sub(r'\D', '', normalized)
        length = normalization_config.get("length", 12)
        if len(normalized) > length:
            normalized = normalized[-length:]
    
    # PAN normalization
    elif norm_type == "pan":
        if normalization_config.get("uppercase", False):
            normalized = normalized.upper()
    
    # GST normalization
    elif norm_type == "gst":
        if normalization_config.get("uppercase", False):
            normalized = normalized.upper()
    
    # IFSC normalization
    elif norm_type == "ifsc":
        if normalization_config.get("uppercase", False):
            normalized = normalized.upper()
    
    # Vehicle normalization
    elif norm_type == "vehicle":
        if normalization_config.get("uppercase", False):
            normalized = normalized.upper()
    
    return normalized

# ====================== HELPERS ======================
def remove_branding(data, extra_blacklist=None):
    if extra_blacklist is None:
        extra_blacklist = []
    blacklist = set([t.lower() for t in GLOBAL_BLACKLIST] + [t.lower() for t in extra_blacklist])
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return [remove_branding(i, extra_blacklist) for i in data if remove_branding(i, extra_blacklist) not in ("", None)]
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if k.lower() in blacklist:
                continue
            val = remove_branding(v, extra_blacklist)
            if val not in ("", None):
                cleaned[k] = val
        return cleaned
    return data

async def get_cached(key):
    if key in cache and time.time() - cache[key][0] < CACHE_TTL:
        return cache[key][1]
    return None

async def set_cached(key, data):
    cache[key] = (time.time(), data)

# ====================== QUART ROUTES ======================
@app.route('/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

@app.route('/api/v1/<api_type>')
async def proxy_api(api_type):
    if api_type not in API_ENDPOINTS:
        return jsonify({"error": "Invalid API type"}), 400
    
    cfg = API_ENDPOINTS[api_type]
    
    # Check API status from database
    api_status = await get_api_status(api_type)
    if not api_status.get("is_enabled", True):
        return jsonify({"error": "This API is currently disabled."}), 503
    if api_status.get("maintenance_mode", False):
        msg = api_status.get("maintenance_message", "⚠️ This API is currently under maintenance. Please try again later.")
        return jsonify({"error": msg}), 503
    
    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    valid, uid, rate_limit = await validate_api_key(key)
    if not valid:
        custom_msg = await get_custom_response(api_type, "invalid_key_message")
        if custom_msg:
            msg = custom_msg.format(purchase_link=PURCHASE_LINK, renew_link=RENEW_LINK)
            return jsonify({"error": msg}), 403
        return jsonify({"error": "Invalid or expired API key"}), 403

    # Check if key is expired
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT expires_at FROM api_keys WHERE key=$1", key)
        if row and row['expires_at'] < datetime.now(timezone.utc):
            custom_msg = await get_custom_response(api_type, "expired_key_message")
            if custom_msg:
                msg = custom_msg.format(purchase_link=PURCHASE_LINK, renew_link=RENEW_LINK)
                return jsonify({"error": msg}), 403
            return jsonify({"error": "API key expired"}), 403

    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        return jsonify({"error": "No active subscription for this API"}), 403

    # Rate limiting
    rate_key = f"rate_{key}"
    now = time.time()
    if rate_key in cache:
        count, start = cache[rate_key]
        if now - start > 60:
            count = 1
            cache[rate_key] = (count, now)
        else:
            if count >= rate_limit:
                return jsonify({"error": "Rate limit exceeded. Please wait and try again."}), 429
            cache[rate_key] = (count + 1, start)
    else:
        cache[rate_key] = (1, now)

    # Request quota check
    used, remaining, total = await get_request_stats(key)
    if total is not None and used is not None and used >= total:
        return jsonify({"error": "Request quota exhausted. Please renew your subscription."}), 429

    param_name = cfg['param_name']
    param_value = request.args.get(param_name)
    if not param_value:
        return jsonify({"error": f"Missing '{param_name}' parameter"}), 400
    
    # Apply input normalization
    if 'normalization' in cfg:
        param_value = normalize_input(param_value, cfg['normalization'])
    
    # Validation after normalization
    if 'param_validation' in cfg and not re.match(cfg['param_validation'], param_value):
        return jsonify({"error": f"Invalid {param_name} format. Please provide a valid input."}), 400

    cache_key = f"api_{api_type}_{param_value}"
    cached = await get_cached(cache_key)
    if cached:
        await increment_request_count(key)
        return app.response_class(response=cached, status=200, mimetype='application/json')

    # Build URL
    if cfg.get('external_api_key'):
        url = cfg['url_template'].format(api_key=cfg['external_api_key'], param=param_value)
    else:
        url = cfg['url_template'].format(param=param_value)

    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                friendly_error = decode_error(error_text)
                return jsonify({"error": friendly_error}), 502
            data = await resp.json()
    except asyncio.TimeoutError:
        return jsonify({"error": "Request timeout. Please try again later."}), 504
    except aiohttp.ClientError as e:
        return jsonify({"error": f"Connection error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": decode_error(str(e))}), 502

    cleaned = remove_branding(data, cfg.get('extra_blacklist', []))

    # ============ IP LOOKUP & DB LOGGING ============
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    async def background_log():
        try:
            ip_info = {"ip": client_ip}
            try:
                ip_url = IP_API_URL.format(client_ip) if IP_API_URL else f"http://ip-api.com/json/{client_ip}"
                async with http_session.get(ip_url, timeout=aiohttp.ClientTimeout(total=5)) as ip_resp:
                    if ip_resp.status == 200:
                        ip_info = await ip_resp.json()
            except Exception as e:
                logger.warning(f"IP lookup failed: {e}")

            await insert_api_log(
                api_type=api_type,
                api_key=key,
                input_value=param_value,
                client_ip=client_ip,
                ip_info=ip_info,
                response_data=cleaned
            )
        except Exception as e:
            logger.error(f"Background log error: {e}")

    asyncio.create_task(background_log())
    # ============ END IP LOOKUP & DB LOGGING ============

    cleaned['branding'] = BRANDING
    pretty = json.dumps(cleaned, indent=2, ensure_ascii=False)
    await set_cached(cache_key, pretty)
    await increment_request_count(key)
    return app.response_class(response=pretty, status=200, mimetype='application/json')

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = await request.get_json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

# ====================== KEYBOARDS ======================
def main_menu(is_admin_flag, is_prem):
    btns = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="menu_genkey"),
         InlineKeyboardButton("📘 API Docs", callback_data="menu_apihelp")],
        [InlineKeyboardButton("👤 My Keys", callback_data="menu_mykeys"),
         InlineKeyboardButton("💰 Balance & Plans", callback_data="menu_balance")],
        [InlineKeyboardButton("🔗 Referral", callback_data="menu_referral"),
         InlineKeyboardButton("🎟️ Redeem Code", callback_data="menu_redeem")]
    ]
    if is_admin_flag or is_prem:
        btns.append([InlineKeyboardButton("🎨 Custom Key", callback_data="menu_customkey")])
    if is_admin_flag:
        btns.append([
            InlineKeyboardButton("🛡️ Admin Panel", callback_data="menu_admin"),
            InlineKeyboardButton("⚙️ Custom Responses", callback_data="menu_custom_responses")
        ])
    return InlineKeyboardMarkup(btns)

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔑 All Keys", callback_data="admin_keys"),
         InlineKeyboardButton("💳 Add Credits", callback_data="admin_addcredits")],
        [InlineKeyboardButton("⭐ Premium", callback_data="admin_premium"),
         InlineKeyboardButton("🎟️ Redeem Code", callback_data="admin_genredeem")],
        [InlineKeyboardButton("👑 Admins", callback_data="admin_admins"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Pricing", callback_data="admin_pricing"),
         InlineKeyboardButton("📨 DM", callback_data="admin_dm")],
        [InlineKeyboardButton("📨 Bulk DM", callback_data="admin_bulkdm"),
         InlineKeyboardButton("🎨 Custom Key", callback_data="admin_customkey")],
        [InlineKeyboardButton("📋 Download Logs", callback_data="admin_download_logs"),
         InlineKeyboardButton("⚙️ Custom Responses", callback_data="admin_custom_responses")],
        [InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ])

back_btn = lambda data: InlineKeyboardButton("🔙 Back", callback_data=data)

# ====================== FORCE JOIN ======================
async def check_force_join(user_id):
    if await is_admin(user_id):
        return True, []
    if PREMIUM_EXEMPT_FORCE_JOIN and await is_premium(user_id):
        return True, []
    missing = []
    for ch in FORCE_JOIN_CHANNELS:
        try:
            mem = await application.bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if mem.status in ['left', 'kicked']:
                missing.append(ch)
        except:
            missing.append(ch)
    return len(missing) == 0, missing

async def send_force_join(chat_id, missing):
    text = "⚠️ <b>Please join these channels first:</b>\n\n"
    kb = [[InlineKeyboardButton(f"Join {ch['name']}", url=ch['link'])] for ch in missing]
    kb.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    await application.bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

# ====================== LOGGING ======================
async def log_key_gen(user_id, key, api_type):
    user = await get_user(user_id)
    text = (
        f"🔑 New Key\n"
        f"👤 {user.get('first_name','')} (@{user.get('username','')}) [{user_id}]\n"
        f"🔹 {api_type.upper()}\n"
        f"<code>{key}</code>"
    )
    try:
        await application.bot.send_message(LOG_CHANNEL_ID, text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Log send failed: {e}")

# ====================== COMMAND HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    await update_user_info(uid, user.username, user.first_name, user.last_name)
    if context.args and context.args[0].startswith('ref_'):
        try:
            ref = int(context.args[0][4:])
            if ref != uid and await set_referrer(uid, ref):
                context.user_data['pending_ref'] = ref
        except:
            pass
    joined, missing = await check_force_join(uid)
    if not joined:
        await send_force_join(uid, missing)
        return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)
    if 'pending_ref' in context.user_data:
        ref = context.user_data.pop('pending_ref')
        await add_credits(ref, REFERRAL_REWARD_CREDITS)
        try:
            await application.bot.send_message(ref, f"🎉 +{REFERRAL_REWARD_CREDITS} credits referral bonus!")
        except:
            pass
    is_adm = await is_admin(uid)
    is_prem = await is_premium(uid)
    await update.message.reply_text(f"✨ Welcome, {user.first_name}!", reply_markup=main_menu(is_adm, is_prem))

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = await get_user_credits(uid)
    api_status = []
    for api in API_ENDPOINTS.keys():
        has_sub = await has_active_subscription(uid, api)
        api_status.append(f"{API_ENDPOINTS[api]['name']}: {'✅' if has_sub else '❌'}")
    text = f"💰 Credits: <b>{bal}</b>\n" + "\n".join(api_status[:10]) + ("\n..." if len(api_status) > 10 else "") + "\n\nBuy plan:"
    
    # Show all API plans
    kb = []
    for api in list(API_ENDPOINTS.keys()):
        plan_row = [
            InlineKeyboardButton(f"{API_ENDPOINTS[api]['name']} W", callback_data=f"plan_{api}_weekly"),
            InlineKeyboardButton(f"{API_ENDPOINTS[api]['name']} M", callback_data=f"plan_{api}_monthly")
        ]
        kb.append(plan_row)
    kb.append([back_btn("menu_start")])
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await balance_command(update, context)

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_redeem'] = True
    await update.message.reply_text("Send redeem code:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    me = await application.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await update.message.reply_text(
        f"🔗 Referral link:\n<code>{link}</code>\nEarn {REFERRAL_REWARD_CREDITS} credits per referral.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await is_admin(uid):
        await update.message.reply_text("🛡️ Admin Panel", reply_markup=admin_panel_kb())
    else:
        await update.message.reply_text("Access denied.")

# ====================== CALLBACK HANDLERS ======================
async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    joined, missing = await check_force_join(uid)
    if joined:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)
        await q.edit_message_text("✅ Thank you! Press /start to see menu.")
    else:
        await q.answer("Join all channels first.", show_alert=True)

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = update.effective_user.id
    is_adm = await is_admin(uid)
    is_prem = await is_premium(uid)

    if not is_adm and data not in ["check_join", "close_panel"]:
        joined, missing = await check_force_join(uid)
        if not joined:
            await q.edit_message_text(
                "⚠️ Join all channels first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data="check_join")]])
            )
            return

    if data == "menu_genkey":
        await genkey_menu(update, context)
    elif data == "menu_start":
        await q.edit_message_text(f"✨ Welcome, {update.effective_user.first_name}!", reply_markup=main_menu(is_adm, is_prem))
    elif data == "menu_apihelp":
        await apihelp_menu(update, context)
    elif data == "menu_mykeys":
        await mykeys_menu(update, context)
    elif data == "menu_balance":
        await balance_menu(update, context)
    elif data == "menu_referral":
        await referral_menu(update, context)
    elif data == "menu_redeem":
        await redeem_prompt(update, context)
    elif data == "menu_customkey":
        if is_adm or is_prem:
            await custom_key_start(update, context)
        else:
            await q.answer("No permission.", show_alert=True)
    elif data == "menu_admin":
        if is_adm:
            await q.edit_message_text("🛡️ Admin Panel", reply_markup=admin_panel_kb())
        else:
            await q.answer("Access denied.", show_alert=True)
    elif data == "menu_custom_responses":
        if is_adm:
            await custom_responses_menu(update, context)
        else:
            await q.answer("Access denied.", show_alert=True)
    elif data == "close_panel":
        await q.delete_message()
    elif data.startswith("gen_"):
        await gen_specific_key(update, context)
    elif data.startswith("plan_"):
        await buy_plan(update, context)
    elif data.startswith("userlist_page_"):
        await paginated_user_list(update, context)
    elif data.startswith("premiumlist_page_"):
        await paginated_premium_list(update, context)
    elif data.startswith("adminlist_page_"):
        await paginated_admin_list(update, context)
    elif data.startswith("keys_page_"):
        await paginated_keys_list(update, context)
    elif data.startswith("toggle_ban_"):
        await toggle_ban(update, context)
    elif data.startswith("add_credits_"):
        await add_credits_prompt(update, context)
    elif data.startswith("remove_premium_"):
        await remove_premium_handler(update, context)
    elif data.startswith("make_premium_"):
        await make_premium_prompt(update, context)
    elif data.startswith("userdetail_"):
        await user_detail_popup(update, context)
    elif data.startswith("admintoggle_"):
        await toggle_admin(update, context)
    elif data.startswith("keytoggle_"):
        await toggle_key_status(update, context)
    elif data.startswith("delete_key_"):
        await confirm_delete_key(update, context)
    elif data.startswith("confirm_delete_key_"):
        await execute_delete_key(update, context)
    elif data.startswith("bcast_"):
        await broadcast_type(update, context)
    elif data == "check_join":
        await check_join_cb(update, context)
    elif data == "admin_customkey":
        await custom_key_admin(update, context)
    elif data.startswith("custkey_"):
        await custom_key_type_selected(update, context)
    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text("Send user ID to add premium:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))
    elif data == "admin_download_logs":
        await download_logs_menu(update, context)
    elif data == "admin_custom_responses":
        await custom_responses_menu(update, context)
    elif data.startswith("cr_api_"):
        await custom_responses_select_api(update, context)
    elif data.startswith("cr_type_"):
        await custom_responses_select_type(update, context)
    elif data.startswith("cr_edit_"):
        await custom_responses_edit(update, context)
    elif data.startswith("api_toggle_"):
        await api_toggle(update, context)
    elif data.startswith("api_maintenance_"):
        await api_maintenance(update, context)
    else:
        await q.answer("Not implemented.", show_alert=True)

# ====================== SUB MENUS ======================
async def genkey_menu(update, context):
    q = update.callback_query
    uid = update.effective_user.id
    has_any = False
    for api in API_ENDPOINTS.keys():
        if await has_active_subscription(uid, api):
            has_any = True
            break
    if not await is_admin(uid) and not has_any:
        await q.edit_message_text("❌ No subscription. Buy a plan first.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
        return
    kb = []
    for api in API_ENDPOINTS.keys():
        kb.append([InlineKeyboardButton(API_ENDPOINTS[api]['name'], callback_data=f"gen_{api}")])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text("Select API to generate key:", reply_markup=InlineKeyboardMarkup(kb))

async def gen_specific_key(update, context):
    q = update.callback_query
    await q.answer()
    api_type = q.data.split('_')[1]
    uid = update.effective_user.id
    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        await q.edit_message_text("❌ No subscription for this API.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_genkey")]]))
        return
    key = await generate_random_key()
    await create_api_key(key, uid, expires_days=30, rate_limit=80, custom_name=f"{api_type.upper()}_Key")
    await log_key_gen(uid, key, api_type)
    ex = API_ENDPOINTS[api_type]['param_example']
    param_name = API_ENDPOINTS[api_type]['param_name']
    ep = f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}?key={key}&{param_name}={ex}"
    await q.edit_message_text(
        f"✅ Key: <code>{key}</code>\nExample:\n<code>{ep}</code>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_genkey")]])
    )

async def custom_key_start(update, context):
    q = update.callback_query
    kb = []
    for api in API_ENDPOINTS.keys():
        kb.append([InlineKeyboardButton(API_ENDPOINTS[api]['name'], callback_data=f"custkey_{api}")])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text("Select API for custom key:", reply_markup=InlineKeyboardMarkup(kb))

async def custom_key_type_selected(update, context):
    q = update.callback_query
    await q.answer()
    api = q.data.split('_')[1]
    context.user_data['custkey_api'] = api
    context.user_data['admin_state'] = 'awaiting_custom_key_string'
    await q.edit_message_text("Send your desired API key (any non-empty string):", reply_markup=InlineKeyboardMarkup([[back_btn("menu_customkey")]]))

async def custom_key_admin(update, context):
    await custom_key_start(update, context)

async def apihelp_menu(update, context):
    q = update.callback_query
    text = "📘 <b>API Docs</b>\n\n"
    for k, v in API_ENDPOINTS.items():
        param_name = v['param_name']
        text += f"<b>{v['name']}</b>\n<code>{RENDER_EXTERNAL_URL}/api/v1/{k}?key=KEY&{param_name}={v['param_example']}</code>\n\n"
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

async def mykeys_menu(update, context):
    q = update.callback_query
    uid = update.effective_user.id
    keys = await list_api_keys(uid)
    text = "🔑 <b>Your Keys</b>\n\n"
    kb = []
    if not keys:
        text = "No keys found."
    else:
        for row in keys:
            status = "✅" if row['is_active'] else "❌"
            req_info = ""
            if row['total_requests_allowed'] is not None:
                remaining = max(0, row['total_requests_allowed'] - row['requests_made'])
                req_info = f" | Req: {remaining}/{row['total_requests_allowed']}"
            else:
                req_info = " | Req: ∞"
            text += f"{status} <code>{row['key'][:20]}...</code> Exp: {row['expires_at'].strftime('%Y-%m-%d')}{req_info}\n"
            kb.append([InlineKeyboardButton(f"🗑 Delete {row['key'][:10]}...", callback_data=f"delete_key_{row['key']}")])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def balance_menu(update, context):
    q = update.callback_query
    uid = update.effective_user.id
    bal = await get_user_credits(uid)
    api_status = []
    for api in API_ENDPOINTS.keys():
        has_sub = await has_active_subscription(uid, api)
        api_status.append(f"{API_ENDPOINTS[api]['name']}: {'✅' if has_sub else '❌'}")
    text = f"💰 Credits: <b>{bal}</b>\n" + "\n".join(api_status[:10]) + ("\n..." if len(api_status) > 10 else "") + "\n\nBuy plan:"
    kb = []
    for api in list(API_ENDPOINTS.keys()):
        kb.append([
            InlineKeyboardButton(f"{API_ENDPOINTS[api]['name']} W", callback_data=f"plan_{api}_weekly"),
            InlineKeyboardButton(f"{API_ENDPOINTS[api]['name']} M", callback_data=f"plan_{api}_monthly")
        ])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def buy_plan(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split('_')
    api_type = parts[1]
    plan = parts[2]
    uid = update.effective_user.id
    if await is_admin(uid):
        pl = await get_plan(api_type, plan)
        if pl:
            async with pool.acquire() as conn:
                start = datetime.now(timezone.utc)
                end = start + timedelta(days=pl['duration_days'])
                await conn.execute(
                    "INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) VALUES ($1,$2,$3,$4,$5,TRUE)",
                    uid, api_type, pl['plan_id'], start, end
                )
            await q.edit_message_text("✅ Admin plan activated.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
        else:
            await q.answer("Plan error.", show_alert=True)
        return
    pl = await get_plan(api_type, plan)
    if not pl:
        await q.answer("Plan not found.", show_alert=True)
        return
    bal = await get_user_credits(uid)
    if bal < pl['price_credits']:
        await q.answer(f"Need {pl['price_credits']} credits.", show_alert=True)
        return
    if await create_subscription(uid, api_type, plan):
        await q.edit_message_text(f"✅ Purchased {API_ENDPOINTS[api_type]['name']} {plan} plan.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
    else:
        await q.answer("Failed.", show_alert=True)

async def referral_menu(update, context):
    q = update.callback_query
    uid = update.effective_user.id
    me = await application.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await q.edit_message_text(
        f"🔗 Link:\n<code>{link}</code>\nEarn {REFERRAL_REWARD_CREDITS} credits.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def redeem_prompt(update, context):
    q = update.callback_query
    context.user_data['awaiting_redeem'] = True
    await q.edit_message_text("Send redeem code:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

# ====================== ADMIN PANEL HANDLERS ======================
async def admin_menu_handler(update, context):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "admin_users":
        await show_user_list(update, context, 0)
    elif data == "admin_keys":
        await show_keys_list(update, context, 0)
    elif data == "admin_addcredits":
        context.user_data['admin_state'] = 'awaiting_user_for_credits'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_premium":
        await show_premium_list(update, context, 0)
    elif data == "admin_genredeem":
        context.user_data['admin_state'] = 'awaiting_redeem_credits'
        await q.edit_message_text("Credits amount:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_admins":
        await show_admin_list(update, context, 0)
    elif data == "admin_stats":
        total = await count_users()
        async with pool.acquire() as conn:
            keys = await conn.fetchval("SELECT COUNT(*) FROM api_keys")
            prem = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
            logs = await count_api_logs()
        await q.edit_message_text(
            f"📊 Users: {total}\nKeys: {keys}\nPremium: {prem}\nLogs: {logs}",
            reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]])
        )
    elif data == "admin_dm":
        context.user_data['admin_state'] = 'awaiting_dm_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_bulkdm":
        context.user_data['admin_state'] = 'awaiting_bulkdm_ids'
        await q.edit_message_text("Send comma-separated IDs or text file:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_broadcast":
        await q.edit_message_text(
            "📢 Send your message (text, photo, video, document, audio, media group) and I'll broadcast it automatically.",
            reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]])
        )
    elif data == "admin_pricing":
        await pricing_menu(update, context)
    elif data == "admin_customkey":
        await custom_key_admin(update, context)
    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))
    elif data == "admin_download_logs":
        await download_logs_menu(update, context)
    elif data == "admin_custom_responses":
        await custom_responses_menu(update, context)
    elif data.startswith("price_"):
        await pricing_select_api(update, context)
    elif data.startswith("plan_price_"):
        await pricing_edit(update, context)
    else:
        await q.answer("Coming soon.", show_alert=True)

# ====================== PRICING MANAGEMENT ======================
async def pricing_menu(update, context):
    q = update.callback_query
    kb = []
    for api in API_ENDPOINTS.keys():
        kb.append([InlineKeyboardButton(f"💰 {API_ENDPOINTS[api]['name']}", callback_data=f"price_{api}")])
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text("⚙️ <b>Pricing Management</b>\n\nSelect API to edit pricing:", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def pricing_select_api(update, context):
    q = update.callback_query
    api = q.data.split('_')[1]
    plans = await get_all_plans(api)
    text = f"💰 <b>{API_ENDPOINTS[api]['name']} - Pricing</b>\n\n"
    kb = []
    for plan in plans:
        status = "✅" if plan['is_active'] else "❌"
        text += f"{status} {plan['plan_name'].title()}: {plan['price_credits']} credits ({plan['duration_days']} days)\n"
        kb.append([
            InlineKeyboardButton(f"✏️ Edit {plan['plan_name'].title()}", callback_data=f"plan_price_{api}_{plan['plan_name']}"),
            InlineKeyboardButton(f"{'Enable' if not plan['is_active'] else 'Disable'}", callback_data=f"plan_toggle_{api}_{plan['plan_name']}")
        ])
    kb.append([back_btn("admin_pricing")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def pricing_edit(update, context):
    q = update.callback_query
    parts = q.data.split('_')
    api = parts[2]
    plan = parts[3]
    context.user_data['pricing_api'] = api
    context.user_data['pricing_plan'] = plan
    context.user_data['admin_state'] = 'awaiting_pricing_credits'
    await q.edit_message_text(f"Enter new price (credits) for {API_ENDPOINTS[api]['name']} - {plan.title()}:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_pricing")]]))

# ====================== CUSTOM RESPONSES MENU ======================
async def custom_responses_menu(update, context):
    q = update.callback_query
    kb = [
        [InlineKeyboardButton("📝 Edit Responses", callback_data="cr_edit_default")],
        [InlineKeyboardButton("🔧 API Status Management", callback_data="cr_api_status")],
        [back_btn("menu_admin")]
    ]
    await q.edit_message_text("⚙️ <b>Custom Responses & API Management</b>\n\nManage custom messages and API status.", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def custom_responses_select_api(update, context):
    q = update.callback_query
    api = q.data.split('_')[2]
    context.user_data['cr_api'] = api
    kb = [
        [InlineKeyboardButton("🔑 Expired Key", callback_data=f"cr_type_expired_key")],
        [InlineKeyboardButton("❌ Invalid Key", callback_data=f"cr_type_invalid_key")],
        [InlineKeyboardButton("🔧 Maintenance", callback_data=f"cr_type_maintenance")],
        [InlineKeyboardButton("⚠️ Warning", callback_data=f"cr_type_warning")],
        [InlineKeyboardButton("🚫 Outage", callback_data=f"cr_type_outage")],
        [InlineKeyboardButton("📢 Promotional", callback_data=f"cr_type_promotional")],
        [back_btn("menu_custom_responses")]
    ]
    await q.edit_message_text(f"Select response type for <b>{api.upper()}</b>:", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def custom_responses_select_type(update, context):
    q = update.callback_query
    response_type = q.data.split('_')[2]
    context.user_data['cr_type'] = response_type
    api = context.user_data.get('cr_api', 'default')
    
    # Get current message
    current = await get_custom_response(api, response_type)
    
    context.user_data['admin_state'] = 'awaiting_custom_response'
    await q.edit_message_text(
        f"Current message for <b>{response_type.replace('_', ' ').title()}</b>:\n\n<code>{current or 'Not set'}</code>\n\nSend new message (use {{renew_link}} and {{purchase_link}} as variables):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_custom_responses")]])
    )

async def custom_responses_edit(update, context):
    q = update.callback_query
    # This is handled in text handler
    await q.answer()

async def api_toggle(update, context):
    q = update.callback_query
    api = q.data.split('_')[2]
    status = await get_api_status(api)
    new_status = not status.get('is_enabled', True)
    await set_api_status(api, is_enabled=new_status)
    await q.answer(f"API {api.upper()} {'enabled' if new_status else 'disabled'}.", show_alert=True)
    await api_status_list(update, context)

async def api_maintenance(update, context):
    q = update.callback_query
    api = q.data.split('_')[2]
    status = await get_api_status(api)
    new_status = not status.get('maintenance_mode', False)
    await set_api_status(api, maintenance_mode=new_status)
    await q.answer(f"Maintenance mode {'enabled' if new_status else 'disabled'} for {api.upper()}.", show_alert=True)
    await api_status_list(update, context)

async def api_status_list(update, context):
    q = update.callback_query
    statuses = await list_all_api_status()
    text = "🔧 <b>API Status</b>\n\n"
    kb = []
    for row in statuses:
        api = row['api_type']
        enabled = "✅" if row['is_enabled'] else "❌"
        maintenance = "🔧" if row['maintenance_mode'] else "✓"
        text += f"{enabled} {api.upper()} {maintenance}\n"
        kb.append([
            InlineKeyboardButton(f"Toggle {api.upper()}", callback_data=f"api_toggle_{api}"),
            InlineKeyboardButton(f"Maintenance {api.upper()}", callback_data=f"api_maintenance_{api}")
        ])
    kb.append([back_btn("menu_custom_responses")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

# ====================== PAGINATION VIEWS ======================
async def show_user_list(update, context, page):
    q = update.callback_query
    limit = 10
    offset = page * limit
    users = await get_users_paginated(offset, limit)
    total = await count_users()
    pages = max((total + limit - 1) // limit, 1)
    text = f"👥 <b>Users (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for u in users:
        uid = u['user_id']
        uname = u['username']
        fname = u['first_name']
        banned = u['is_banned']
        prem = u['is_premium']
        creds = u['credits']
        name = fname or str(uid)
        stat = "🚫" if banned else ("⭐" if prem else "✅")
        kb.append([InlineKeyboardButton(f"{stat} {name} | 💰{creds}", callback_data=f"userdetail_{uid}")])
        row = []
        row.append(InlineKeyboardButton("🚫" if not banned else "✅", callback_data=f"toggle_ban_{uid}"))
        row.append(InlineKeyboardButton("💳", callback_data=f"add_credits_{uid}"))
        row.append(InlineKeyboardButton("⭐" if prem else "⭐", callback_data=f"{'remove_premium_' if prem else 'make_premium_'}{uid}"))
        kb.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"userlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"userlist_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_user_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_user_list(update, context, page)

async def user_detail_popup(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[1])
    user = await get_user(uid)
    text = f"👤 {user.get('first_name','N/A')} (@{user.get('username','')})\nID: {uid}\nCredits: {user['credits']}\nPremium: {'Yes' if user['is_premium'] else 'No'}\nBanned: {'Yes' if user['is_banned'] else 'No'}"
    await q.answer(text, show_alert=True)

async def show_premium_list(update, context, page):
    q = update.callback_query
    limit = 10
    offset = page * limit
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, username, first_name, premium_expiry FROM users WHERE is_premium=TRUE ORDER BY user_id LIMIT $1 OFFSET $2",
            limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
    pages = max((total + limit - 1) // limit, 1)
    text = f"⭐ <b>Premium Users (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for u in rows:
        uid = u['user_id']
        uname = u['username']
        fname = u['first_name']
        exp = u['premium_expiry']
        name = fname or str(uid)
        exp_str = exp.strftime('%Y-%m-%d') if exp else 'Permanent'
        kb.append([InlineKeyboardButton(f"{name} | Exp: {exp_str}", callback_data=f"premdetail_{uid}")])
        kb.append([InlineKeyboardButton("❌ Remove", callback_data=f"remove_premium_{uid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"premiumlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"premiumlist_page_{page+1}"))
    if nav:
        kb.append(nav)
    # Add Premium button
    kb.append([InlineKeyboardButton("➕ Add Premium", callback_data="admin_addpremium")])
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_premium_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_premium_list(update, context, page)

async def show_admin_list(update, context, page):
    q = update.callback_query
    limit = 10
    offset = page * limit
    admins = await get_admins_paginated(offset, limit)
    total = await count_admins()
    pages = max((total + limit - 1) // limit, 1)
    text = f"👑 <b>Admins (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for a in admins:
        uid = a['user_id']
        uname = a['username']
        fname = a['first_name']
        name = fname or str(uid)
        kb.append([InlineKeyboardButton(f"{name}", callback_data=f"admindetail_{uid}")])
        if uid != OWNER_ID:
            kb.append([InlineKeyboardButton("❌ Demote", callback_data=f"admintoggle_{uid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"adminlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"adminlist_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_admin_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_admin_list(update, context, page)

async def show_keys_list(update, context, page):
    q = update.callback_query
    limit = 10
    offset = page * limit
    keys = await list_all_keys_full()
    total = len(keys)
    pages = max((total + limit - 1) // limit, 1)
    start_idx = page * limit
    end_idx = min(start_idx + limit, total)
    current_keys = keys[start_idx:end_idx]
    
    text = f"🔑 <b>All Keys (Page {page+1}/{pages})</b>\n\n"
    kb = []
    
    # If too many keys, send as file
    if total > 50:
        key_data = [dict(k) for k in keys]
        json_data = json.dumps(key_data, indent=2, default=str)
        filename = f"all_keys_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        await application.bot.send_document(chat_id=q.from_user.id, document=json_data.encode('utf-8'), filename=filename)
        await q.edit_message_text(f"📄 Total {total} keys found. Sent as JSON file.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
        return
    
    for k in current_keys:
        status = "✅" if k['is_active'] else "❌"
        req_info = ""
        if k['total_requests_allowed'] is not None:
            remaining = max(0, k['total_requests_allowed'] - k['requests_made'])
            req_info = f" | Req: {remaining}/{k['total_requests_allowed']}"
        else:
            req_info = " | Req: ∞"
        text += f"{status} <code>{k['key']}</code> | User: {k['created_by']} | Exp: {k['expires_at'].strftime('%Y-%m-%d')}{req_info}\n"
        kb.append([InlineKeyboardButton(f"{'Deactivate' if k['is_active'] else 'Activate'}", callback_data=f"keytoggle_{k['key']}")])
        kb.append([InlineKeyboardButton(f"🗑 Delete", callback_data=f"delete_key_{k['key']}")])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"keys_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"keys_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_keys_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_keys_list(update, context, page)

# ====================== ACTION HANDLERS ======================
async def toggle_ban(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = NOT is_banned WHERE user_id=$1", uid)
        banned = await conn.fetchval("SELECT is_banned FROM users WHERE user_id=$1", uid)
    await q.answer(f"User {'banned' if banned else 'unbanned'}.", show_alert=True)
    await show_user_list(update, context, 0)

async def add_credits_prompt(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    context.user_data['target_user'] = uid
    context.user_data['admin_state'] = 'awaiting_credit_amount'
    await q.edit_message_text(f"Amount to add for {uid}:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_users")]]))

async def remove_premium_handler(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    await remove_premium(uid)
    await q.answer("Premium removed.", show_alert=True)
    await show_premium_list(update, context, 0)

async def make_premium_prompt(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    context.user_data['target_premium_user'] = uid
    context.user_data['admin_state'] = 'awaiting_premium_days'
    await q.edit_message_text(f"Days for premium (or 'permanent'):", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))

async def toggle_admin(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[1])
    if uid == OWNER_ID:
        await q.answer("Cannot demote main owner.", show_alert=True)
        return
    is_owner = await is_admin(uid)
    await set_admin(uid, not is_owner)
    await q.answer(f"Admin {'removed' if is_owner else 'added'}.", show_alert=True)
    await show_admin_list(update, context, 0)

async def toggle_key_status(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split('_', 1)[1]
    async with pool.acquire() as conn:
        active = await conn.fetchval("SELECT is_active FROM api_keys WHERE key=$1", key)
    if active:
        await deactivate_api_key(key)
        await q.answer("Key deactivated.", show_alert=True)
    else:
        await activate_api_key(key)
        await q.answer("Key activated.", show_alert=True)
    await show_keys_list(update, context, 0)

# ====================== DELETE KEY ======================
async def confirm_delete_key(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("delete_key_", 1)[1]
    context.user_data['del_key'] = key
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_delete_key_{key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_panel")]
    ])
    await q.edit_message_text(f"Delete key <code>{key[:20]}...</code>?", parse_mode='HTML', reply_markup=kb)

async def execute_delete_key(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("confirm_delete_key_", 1)[1]
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM api_keys WHERE key=$1", key)
    await q.edit_message_text(f"✅ Key deleted: <code>{key[:20]}...</code>", parse_mode='HTML')

# ====================== SMART BROADCAST ======================
async def broadcast_type(update, context):
    context.user_data['broadcast_mode'] = True
    await update.callback_query.edit_message_text(
        "📢 Send your message (text, photo, video, document, audio, media group) and I'll broadcast it automatically.",
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]])
    )

async def handle_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    if not context.user_data.get('broadcast_mode'):
        return
    
    msg = update.message
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned=FALSE")
    users = [r['user_id'] for r in rows]
    success = 0
    
    for uid in users:
        try:
            if msg.text and not msg.photo and not msg.video and not msg.document and not msg.audio:
                # Text message
                await application.bot.send_message(uid, msg.text, parse_mode='HTML')
            elif msg.photo:
                # Photo with optional caption
                await application.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                await application.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif msg.document:
                await application.bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            elif msg.audio:
                await application.bot.send_audio(uid, msg.audio.file_id, caption=msg.caption or "")
            elif msg.media_group_id:
                # Handle media group - send first media
                if msg.photo:
                    await application.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.video:
                    await application.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            success += 1
        except Exception as e:
            logger.error(f"Broadcast error to {uid}: {e}")
        await asyncio.sleep(0.05)
    
    context.user_data.pop('broadcast_mode', None)
    await update.message.reply_text(f"✅ Broadcast to {success}/{len(users)} users.")

# ====================== DOWNLOAD LOGS ======================
async def download_logs_menu(update, context):
    q = update.callback_query
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Download as CSV", callback_data="dl_logs_csv")],
        [InlineKeyboardButton("📃 Download as JSON", callback_data="dl_logs_json")],
        [back_btn("menu_admin")]
    ])
    await q.edit_message_text("📋 Download API Logs\nChoose format:", reply_markup=kb)

async def download_logs_callback(update, context):
    q = update.callback_query
    data = q.data
    if data == "dl_logs_csv":
        logs = await get_api_logs(limit=5000)
        if not logs:
            await q.edit_message_text("No logs found.", reply_markup=InlineKeyboardMarkup([[back_btn("admin_download_logs")]]))
            return
        headers = list(logs[0].keys())
        lines = [','.join(headers)]
        for row in logs:
            values = [str(row[h]).replace(",", "\\,") if row[h] is not None else "" for h in headers]
            lines.append(','.join(values))
        csv_data = '\n'.join(lines)
        filename = f"api_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        await application.bot.send_document(chat_id=q.from_user.id, document=csv_data.encode('utf-8'), filename=filename)
        await q.edit_message_text("✅ Logs sent as CSV.", reply_markup=InlineKeyboardMarkup([[back_btn("admin_download_logs")]]))
    elif data == "dl_logs_json":
        logs = await get_api_logs(limit=5000)
        if not logs:
            await q.edit_message_text("No logs found.", reply_markup=InlineKeyboardMarkup([[back_btn("admin_download_logs")]]))
            return
        data = [dict(row) for row in logs]
        for entry in data:
            for k, v in entry.items():
                if isinstance(v, datetime):
                    entry[k] = v.isoformat()
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        filename = f"api_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        await application.bot.send_document(chat_id=q.from_user.id, document=json_data.encode('utf-8'), filename=filename)
        await q.edit_message_text("✅ Logs sent as JSON.", reply_markup=InlineKeyboardMarkup([[back_btn("admin_download_logs")]]))

# ====================== TEXT MESSAGE HANDLER ======================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get('awaiting_redeem'):
        context.user_data.pop('awaiting_redeem')
        if await redeem_code(uid, text):
            await update.message.reply_text("✅ Redeemed!")
        else:
            await update.message.reply_text("❌ Invalid/expired code.")
        return

    if not await is_admin(uid):
        return

    state = context.user_data.get('admin_state')
    if not state:
        return

    if state == 'awaiting_user_for_credits':
        try:
            target = int(text)
            context.user_data['target_user'] = target
            context.user_data['admin_state'] = 'awaiting_credit_amount'
            await update.message.reply_text("Amount:")
        except:
            await update.message.reply_text("Invalid ID.")
            context.user_data.pop('admin_state', None)
    elif state == 'awaiting_credit_amount':
        try:
            amt = int(text)
            target = context.user_data.pop('target_user')
            await add_credits(target, amt)
            await update.message.reply_text(f"✅ Added {amt} credits to {target}.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid amount.")
    elif state == 'awaiting_redeem_credits':
        try:
            creds = int(text)
            context.user_data['redeem_creds'] = creds
            context.user_data['admin_state'] = 'awaiting_redeem_maxuses'
            await update.message.reply_text("Max uses:")
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_redeem_maxuses':
        try:
            maxu = int(text)
            creds = context.user_data.pop('redeem_creds')
            code = secrets.token_hex(4).upper()
            await create_redeem_code(code, creds, uid, maxu)
            await update.message.reply_text(f"✅ Code: <code>{code}</code>\nCredits: {creds}\nUses: {maxu}")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_dm_user':
        try:
            target = int(text)
            context.user_data['dm_target'] = target
            context.user_data['admin_state'] = 'awaiting_dm_message'
            await update.message.reply_text("Message:")
        except:
            await update.message.reply_text("Invalid ID.")
    elif state == 'awaiting_dm_message':
        target = context.user_data.pop('dm_target')
        try:
            await application.bot.send_message(target, text, parse_mode='HTML')
            await update.message.reply_text("✅ Sent.")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_bulkdm_ids':
        ids = [int(x.strip()) for x in text.replace('\n', ',').split(',') if x.strip().isdigit()]
        context.user_data['bulk_ids'] = ids
        context.user_data['admin_state'] = 'awaiting_bulkdm_message'
        await update.message.reply_text(f"Got {len(ids)} IDs. Send message:")
    elif state == 'awaiting_bulkdm_message':
        ids = context.user_data.pop('bulk_ids')
        success = 0
        for i in ids:
            try:
                await application.bot.send_message(i, text, parse_mode='HTML')
                success += 1
            except:
                pass
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ Sent to {success}/{len(ids)}.")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_custom_key_string':
        key = text.strip()
        if not key:
            await update.message.reply_text("Key cannot be empty. Send a valid key:")
            return
        exists = await pool.fetchval("SELECT key FROM api_keys WHERE key=$1", key)
        if exists:
            await update.message.reply_text("Key already exists. Choose another.")
            return
        context.user_data['cust_key'] = key
        context.user_data['admin_state'] = 'awaiting_custom_key_expiry'
        await update.message.reply_text("Expiry in days (e.g., 30) or type 'permanent':")
    elif state == 'awaiting_custom_key_expiry':
        if text.lower() == 'permanent':
            context.user_data['cust_expiry'] = 'permanent'
        else:
            try:
                days = int(text)
                if days <= 0:
                    await update.message.reply_text("Days must be positive or type 'permanent'.")
                    return
                context.user_data['cust_expiry'] = days
            except:
                await update.message.reply_text("Invalid number or type 'permanent'.")
                return
        context.user_data['admin_state'] = 'awaiting_custom_key_totalreq'
        await update.message.reply_text("Total requests allowed (0 for unlimited):")
    elif state == 'awaiting_custom_key_totalreq':
        try:
            total = int(text)
            context.user_data['cust_total'] = total if total > 0 else None
        except:
            await update.message.reply_text("Invalid number.")
            return
        context.user_data['admin_state'] = 'awaiting_custom_key_ratelimit'
        await update.message.reply_text("Rate limit per minute:")
    elif state == 'awaiting_custom_key_ratelimit':
        try:
            rate = int(text)
            context.user_data['cust_rate'] = rate
        except:
            await update.message.reply_text("Invalid number.")
            return
        expiry_days = context.user_data['cust_expiry']
        if expiry_days == 'permanent':
            expiry_days = 36500
        await create_api_key(
            context.user_data['cust_key'],
            uid,
            expires_days=expiry_days,
            rate_limit=context.user_data['cust_rate'],
            total_requests=context.user_data['cust_total'],
            custom_name=f"{context.user_data['custkey_api'].upper()}_Custom"
        )
        await log_key_gen(uid, context.user_data['cust_key'], context.user_data['custkey_api'])
        api_type = context.user_data['custkey_api']
        ex = API_ENDPOINTS[api_type]['param_example']
        param_name = API_ENDPOINTS[api_type]['param_name']
        endpoint = f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}?key={context.user_data['cust_key']}&{param_name}={ex}"
        await update.message.reply_text(
            f"✅ <b>Custom Key Created!</b>\n\n"
            f"🔑 <b>Key:</b> <code>{context.user_data['cust_key']}</code>\n"
            f"📅 <b>Expiry:</b> {context.user_data['cust_expiry'] if expiry_days != 36500 else 'Permanent'} days\n"
            f"📊 <b>Requests:</b> {context.user_data['cust_total'] if context.user_data['cust_total'] else 'Unlimited'}\n"
            f"⚡ <b>Rate Limit:</b> {context.user_data['cust_rate']}/min\n\n"
            f"🔗 <b>API Endpoint:</b>\n<code>{endpoint}</code>",
            parse_mode='HTML'
        )
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_pricing_credits':
        try:
            price = int(text)
            api = context.user_data.pop('pricing_api')
            plan = context.user_data.pop('pricing_plan')
            await update_plan_price(api, plan, price)
            await update.message.reply_text(f"✅ Updated {API_ENDPOINTS[api]['name']} {plan.title()} = {price} credits.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_premium_user':
        try:
            target = int(text)
            context.user_data['target_premium_user'] = target
            context.user_data['admin_state'] = 'awaiting_premium_days'
            await update.message.reply_text("Days (or 'permanent'):")
        except:
            await update.message.reply_text("Invalid ID.")
    elif state == 'awaiting_premium_days':
        days_txt = text.lower()
        target = context.user_data.pop('target_premium_user')
        if days_txt == 'permanent':
            await set_premium(target, days=None)
        else:
            try:
                await set_premium(target, days=int(days_txt))
            except:
                await update.message.reply_text("Invalid.")
                return
        await update.message.reply_text(f"✅ Premium set for {target}.")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_custom_response':
        api = context.user_data.get('cr_api', 'default')
        response_type = context.user_data.get('cr_type', 'expired_key_message')
        await set_custom_response(api, response_type, text)
        await update.message.reply_text(f"✅ Custom response updated for {api.upper()} - {response_type.replace('_', ' ').title()}.")
        context.user_data.pop('admin_state', None)
        context.user_data.pop('cr_api', None)
        context.user_data.pop('cr_type', None)

# ====================== BACKGROUND TASKS ======================
async def self_ping():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(SELF_PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(f"{RENDER_EXTERNAL_URL}/health")
            await application.bot.get_me()
        except:
            pass

async def premium_expiry_check():
    while True:
        await asyncio.sleep(3600)
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_premium=FALSE WHERE is_premium=TRUE AND premium_expiry IS NOT NULL AND premium_expiry < NOW()")

async def daily_backup():
    await asyncio.sleep(120)
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
        try:
            csv_data = await export_tables_to_csv()
            for table, content in csv_data.items():
                if not content:
                    continue
                await application.bot.send_document(
                    chat_id=BACKUP_CHAT_ID,
                    document=content.encode('utf-8'),
                    filename=f"{table}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
                    caption=f"📁 {table}"
                )
            await application.bot.send_message(BACKUP_CHAT_ID, "✅ Daily backup complete.")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

# ====================== STARTUP / SHUTDOWN ======================
async def on_startup():
    global http_session
    await init_db()
    global pool
    pool = database.pool
    http_session = aiohttp.ClientSession()
    await application.initialize()
    await application.bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("balance", "Check credits"),
        BotCommand("buy", "Purchase subscription"),
        BotCommand("redeem", "Redeem code"),
        BotCommand("referral", "Referral link"),
        BotCommand("admin", "Admin panel")
    ])
    if BOT_MODE == "webhook":
        await application.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/webhook", secret_token=WEBHOOK_SECRET)
        logger.info(f"Webhook set to {RENDER_EXTERNAL_URL}/webhook")
    else:
        asyncio.create_task(application.run_polling())
        logger.info("Polling started")
    asyncio.create_task(self_ping())
    asyncio.create_task(premium_expiry_check())
    asyncio.create_task(daily_backup())

async def on_shutdown():
    if http_session:
        await http_session.close()
    await application.stop()
    await application.shutdown()
    await close_db()

# ====================== HANDLER REGISTRATION ======================
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("balance", balance_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CommandHandler("redeem", redeem_command))
application.add_handler(CommandHandler("referral", referral_command))
application.add_handler(CommandHandler("admin", admin_command))
application.add_handler(CallbackQueryHandler(menu_router, pattern="^menu_"))
application.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^admin_"))
application.add_handler(CallbackQueryHandler(buy_plan, pattern="^plan_"))
application.add_handler(CallbackQueryHandler(gen_specific_key, pattern="^gen_"))
application.add_handler(CallbackQueryHandler(broadcast_type, pattern="^bcast_"))
application.add_handler(CallbackQueryHandler(check_join_cb, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(paginated_user_list, pattern="^userlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_premium_list, pattern="^premiumlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_admin_list, pattern="^adminlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_keys_list, pattern="^keys_page_"))
application.add_handler(CallbackQueryHandler(toggle_ban, pattern="^toggle_ban_"))
application.add_handler(CallbackQueryHandler(add_credits_prompt, pattern="^add_credits_"))
application.add_handler(CallbackQueryHandler(remove_premium_handler, pattern="^remove_premium_"))
application.add_handler(CallbackQueryHandler(make_premium_prompt, pattern="^make_premium_"))
application.add_handler(CallbackQueryHandler(user_detail_popup, pattern="^userdetail_"))
application.add_handler(CallbackQueryHandler(toggle_admin, pattern="^admintoggle_"))
application.add_handler(CallbackQueryHandler(toggle_key_status, pattern="^keytoggle_"))
application.add_handler(CallbackQueryHandler(confirm_delete_key, pattern="^delete_key_"))
application.add_handler(CallbackQueryHandler(execute_delete_key, pattern="^confirm_delete_key_"))
application.add_handler(CallbackQueryHandler(custom_key_type_selected, pattern="^custkey_"))
application.add_handler(CallbackQueryHandler(download_logs_callback, pattern="^dl_logs_"))
application.add_handler(CallbackQueryHandler(custom_responses_menu, pattern="^menu_custom_responses$"))
application.add_handler(CallbackQueryHandler(pricing_menu, pattern="^admin_pricing$"))
application.add_handler(CallbackQueryHandler(pricing_select_api, pattern="^price_"))
application.add_handler(CallbackQueryHandler(pricing_edit, pattern="^plan_price_"))
application.add_handler(CallbackQueryHandler(api_status_list, pattern="^cr_api_status$"))
application.add_handler(CallbackQueryHandler(custom_responses_select_api, pattern="^cr_api_"))
application.add_handler(CallbackQueryHandler(custom_responses_select_type, pattern="^cr_type_"))
application.add_handler(CallbackQueryHandler(api_toggle, pattern="^api_toggle_"))
application.add_handler(CallbackQueryHandler(api_maintenance, pattern="^api_maintenance_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO, handle_broadcast_media))

if __name__ == '__main__':
    import hypercorn.asyncio
    from hypercorn.config import Config
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(on_startup())
    loop.run_until_complete(hypercorn.asyncio.serve(app, config))
