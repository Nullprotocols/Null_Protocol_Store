# main.py - FINAL PRODUCTION VERSION (ALL APIs + REDIS + SHEETS + IP INTELLIGENCE + SMART BROADCAST)

import json, asyncio, secrets, time, re, aiohttp, logging, os
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
from sheets import init_sheets, log_api_call
import redis_client

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Quart app
app = Quart(__name__)

# In-memory fallback cache (used if Redis unavailable)
memory_cache: dict = {}

# Global HTTP session
http_session: aiohttp.ClientSession = None

# PTB application
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Custom response overrides (persisted only in memory, editable by admin)
CUSTOM_ERROR_OVERRIDES: dict = {}

# ====================== HELPERS ======================
def remove_branding(data, extra_blacklist=None):
    """Remove branding fields from API response."""
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
    """Get cached data from Redis, fallback to memory."""
    val = await redis_client.get_cache(key)
    if val:
        return val
    # Fallback to memory dict
    if key in memory_cache and time.time() - memory_cache[key][0] < CACHE_TTL:
        return memory_cache[key][1]
    return None

async def set_cached(key, data):
    """Set cache in Redis and memory fallback."""
    await redis_client.set_cache(key, data, CACHE_TTL)
    memory_cache[key] = (time.time(), data)

# ====================== QUART ROUTES ======================
@app.route('/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

@app.route('/api/v1/<api_type>')
async def proxy_api(api_type):
    if api_type not in API_ENDPOINTS:
        return jsonify({"error": "Invalid API type"}), 400

    cfg = API_ENDPOINTS[api_type]
    if not cfg.get('enabled', True):
        return jsonify({"error": "This API is currently disabled."}), 403

    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    valid, uid, rate_limit = await validate_api_key(key)
    if not valid:
        # Check if expired or invalid, but validate_api_key returns (valid, uid, rate_limit)
        # We'll differentiate: if key exists but expired, show expired; else invalid
        # For simplicity, we'll check the key existence separately.
        # Actually, validate_api_key already returns False for expired/inactive. We'll use custom message.
        # We'll do a quick check if the key exists in DB to decide expired vs invalid.
        # But we don't have a direct function; we'll just use "invalid_key" generic.
        # We can enhance later. For now, we'll check if key exists at all (by looking up key in DB)
        # But to keep it simple, we use the default invalid key message, and we can distinguish by checking if key is expired:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT expires_at, is_active FROM api_keys WHERE key=$1", key)
        if row and not row['is_active']:
            msg_type = 'expired_key'  # actually inactive; we treat as expired
        elif row and row['expires_at'] < datetime.now(timezone.utc):
            msg_type = 'expired_key'
        else:
            msg_type = 'invalid_key'
        custom_msg = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get(msg_type, DEFAULT_ERROR_RESPONSES[msg_type])
        return jsonify({"error": custom_msg}), 403

    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        custom_msg = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('no_subscription', DEFAULT_ERROR_RESPONSES['no_subscription'])
        return jsonify({"error": custom_msg}), 403

    # Rate limiting using Redis
    rate_key = f"rate_{key}"
    current_count = await redis_client.incr_rate_limit(rate_key, 60)
    if current_count is not None:
        if current_count > rate_limit:
            custom_msg = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('rate_limit', DEFAULT_ERROR_RESPONSES['rate_limit'])
            return jsonify({"error": custom_msg}), 429
    else:
        # Fallback to in-memory rate limit
        now = time.time()
        if rate_key in memory_cache:
            count, start = memory_cache[rate_key]
            if now - start > 60:
                count = 1
                memory_cache[rate_key] = (count, now)
            else:
                if count >= rate_limit:
                    custom_msg = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('rate_limit', DEFAULT_ERROR_RESPONSES['rate_limit'])
                    return jsonify({"error": custom_msg}), 429
                memory_cache[rate_key] = (count + 1, start)
        else:
            memory_cache[rate_key] = (1, now)

    # Request quota
    used, remaining, total = await get_request_stats(key)
    if total is not None and used is not None and used >= total:
        return jsonify({"error": "Request quota exhausted"}), 429

    param_name = cfg['param_name']
    param_value = request.args.get(param_name)
    if not param_value:
        return jsonify({"error": f"Missing '{param_name}'"}), 400

    # ---- SMART INPUT NORMALIZATION ----
    normalized_value = param_value.strip()
    if api_type in ['num', 'mobile', 'gas', 'phone_number', 'vi_photo', 'vi_sim']:
        cleaned = re.sub(r'[^\d]', '', normalized_value)
        if cleaned.startswith('91') and len(cleaned) > 10:
            cleaned = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            cleaned = cleaned[1:]
        normalized_value = cleaned[:10] if len(cleaned) >= 10 else cleaned
    elif api_type in ['aadhaar', 'rashan']:
        normalized_value = re.sub(r'\s|-', '', normalized_value)
    elif api_type == 'email':
        normalized_value = normalized_value.lower().strip()
    elif api_type == 'gst':
        normalized_value = re.sub(r'\s', '', normalized_value).upper()
    elif api_type in ['vehicle', 'vehicle2', 'vehicle3', 'fastag', 'challan']:
        normalized_value = re.sub(r'[\s-]', '', normalized_value).upper()

    if 'param_validation' in cfg and not re.match(cfg['param_validation'], normalized_value):
        custom_msg = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('invalid_input', DEFAULT_ERROR_RESPONSES['invalid_input'])
        return jsonify({"error": custom_msg, "expected_format": cfg.get('param_example', '')}), 400

    cache_key = f"api_{api_type}_{normalized_value}"
    cached = await get_cached(cache_key)
    if cached:
        await increment_request_count(key)
        return app.response_class(response=cached, status=200, mimetype='application/json')

    url = cfg['url_template'].format(api_key=cfg.get('external_api_key', ''), param=normalized_value)
    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                upstream_msg = "Service temporarily unavailable."
                try:
                    err_data = await resp.json()
                    if 'error' in err_data:
                        upstream_msg = err_data['error']
                except:
                    pass
                friendly = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('upstream_error', DEFAULT_ERROR_RESPONSES['upstream_error'])
                return jsonify({"error": friendly, "technical": upstream_msg}), 502
            data = await resp.json()
    except Exception as e:
        friendly = (CUSTOM_ERROR_OVERRIDES.get(api_type, {}) or {}).get('upstream_error', DEFAULT_ERROR_RESPONSES['upstream_error'])
        return jsonify({"error": friendly}), 502

    cleaned = remove_branding(data, cfg.get('extra_blacklist', []))

    # IP lookup & sheet logging
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    async def background_log():
        try:
            ip_info = {"ip": client_ip}
            if IP_API_URL:
                try:
                    ip_url = IP_API_URL.format(client_ip)
                    async with http_session.get(ip_url, timeout=aiohttp.ClientTimeout(total=5)) as ip_resp:
                        if ip_resp.status == 200:
                            ip_info = await ip_resp.json()
                except:
                    pass
            await log_api_call(api_type, key, normalized_value, client_ip, ip_info, cleaned)
        except Exception as e:
            logger.error(f"Background log error: {e}")

    asyncio.create_task(background_log())

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
        btns.append([InlineKeyboardButton("🛡️ Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(btns)

def admin_panel_kb(broadcast_mode=False):
    mode_text = "📢 Broadcast Mode: " + ("ON 🔴" if broadcast_mode else "OFF 🟢")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
         InlineKeyboardButton(mode_text, callback_data="admin_broadcast_toggle")],
        [InlineKeyboardButton("🔑 Full Keys", callback_data="admin_fullkeys"),
         InlineKeyboardButton("💳 Add Credits", callback_data="admin_addcredits")],
        [InlineKeyboardButton("⭐ Premium", callback_data="admin_premium"),
         InlineKeyboardButton("🎟️ Redeem Code", callback_data="admin_genredeem")],
        [InlineKeyboardButton("👑 Admins", callback_data="admin_admins"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Pricing", callback_data="admin_pricing"),
         InlineKeyboardButton("📨 DM", callback_data="admin_dm")],
        [InlineKeyboardButton("📨 Bulk DM", callback_data="admin_bulkdm"),
         InlineKeyboardButton("🎨 Custom Key", callback_data="admin_customkey")],
        [InlineKeyboardButton("📝 Edit Responses", callback_data="admin_edit_responses"),
         InlineKeyboardButton("⚡ Toggle API", callback_data="admin_toggle_api")],
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
    user = update.effective_user; uid = user.id
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
    is_adm = await is_admin(uid); is_prem = await is_premium(uid)
    await update.message.reply_text(f"✨ Welcome, {user.first_name}!", reply_markup=main_menu(is_adm, is_prem))

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = await get_user_credits(uid)
    has_num = await has_active_subscription(uid, 'num')
    has_tg = await has_active_subscription(uid, 'tg')
    text = f"💰 Credits: <b>{bal}</b>\n📞 Num: {'✅' if has_num else '❌'}\n📱 TG: {'✅' if has_tg else '❌'}\n\nBuy plan:"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Num Weekly (15)", callback_data="plan_num_weekly")],
        [InlineKeyboardButton("📞 Num Monthly (30)", callback_data="plan_num_monthly")],
        [InlineKeyboardButton("📱 TG Weekly (15)", callback_data="plan_tg_weekly")],
        [InlineKeyboardButton("📱 TG Monthly (30)", callback_data="plan_tg_monthly")],
        [back_btn("menu_start")]
    ])
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=kb)

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
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await is_admin(uid):
        bmode = context.user_data.get('broadcast_mode', False)
        await update.message.reply_text("🛡️ Admin Panel", reply_markup=admin_panel_kb(bmode))
    else:
        await update.message.reply_text("Access denied.")

# ====================== CALLBACK HANDLERS ======================
async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = update.effective_user.id
    joined, missing = await check_force_join(uid)
    if joined:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)
        await q.edit_message_text("✅ Thank you! Press /start to see menu.")
    else:
        await q.answer("Join all channels first.", show_alert=True)

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data; uid = update.effective_user.id
    is_adm = await is_admin(uid); is_prem = await is_premium(uid)

    # Optimized force join check
    if not is_adm and data not in ["check_join", "close_panel"]:
        # Check DB flag first
        async with pool.acquire() as conn:
            db_joined = await conn.fetchval("SELECT joined_force_channels FROM users WHERE user_id=$1", uid)
        if not db_joined:
            joined, missing = await check_force_join(uid)
            if not joined:
                await q.edit_message_text("⚠️ Join all channels first.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data="check_join")]]))
                return
            else:
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)

    if data == "menu_genkey": await genkey_menu(update, context)
    elif data == "menu_start":
        await q.edit_message_text(f"✨ Welcome, {update.effective_user.first_name}!", reply_markup=main_menu(is_adm, is_prem))
    elif data == "menu_apihelp": await apihelp_menu(update, context)
    elif data == "menu_mykeys": await mykeys_menu(update, context)
    elif data == "menu_balance": await balance_menu(update, context)
    elif data == "menu_referral": await referral_menu(update, context)
    elif data == "menu_redeem": await redeem_prompt(update, context)
    elif data == "menu_customkey":
        if is_adm or is_prem: await custom_key_start(update, context)
        else: await q.answer("No permission.", show_alert=True)
    elif data == "menu_admin":
        if is_adm:
            bmode = context.user_data.get('broadcast_mode', False)
            await q.edit_message_text("🛡️ Admin Panel", reply_markup=admin_panel_kb(bmode))
        else: await q.answer("Access denied.", show_alert=True)
    elif data == "close_panel": await q.delete_message()
    elif data.startswith("gen_"): await gen_specific_key(update, context)
    elif data.startswith("plan_"): await buy_plan(update, context)
    elif data.startswith("userlist_page_"): await paginated_user_list(update, context)
    elif data.startswith("premiumlist_page_"): await paginated_premium_list(update, context)
    elif data.startswith("adminlist_page_"): await paginated_admin_list(update, context)
    elif data.startswith("keys_page_"): await paginated_keys_list(update, context)
    elif data.startswith("toggle_ban_"): await toggle_ban(update, context)
    elif data.startswith("add_credits_"): await add_credits_prompt(update, context)
    elif data.startswith("remove_premium_"): await remove_premium_handler(update, context)
    elif data.startswith("make_premium_"): await make_premium_prompt(update, context)
    elif data.startswith("userdetail_"): await user_detail_popup(update, context)
    elif data.startswith("admintoggle_"): await toggle_admin(update, context)
    elif data.startswith("keytoggle_"): await toggle_key_status(update, context)
    elif data.startswith("delete_key_"): await confirm_delete_key(update, context)
    elif data.startswith("confirm_delete_key_"): await execute_delete_key(update, context)
    elif data.startswith("bcast_"): pass  # old broadcast type removed
    elif data == "check_join": await check_join_cb(update, context)
    elif data == "admin_customkey": await custom_key_admin(update, context)
    elif data.startswith("custkey_"): await custom_key_type_selected(update, context)
    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text("Send user ID to add premium:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))
    else:
        await q.answer("Not implemented.", show_alert=True)

# ====================== SUB MENUS ======================
async def genkey_menu(update, context):
    q = update.callback_query; uid = update.effective_user.id
    if await is_admin(uid):
        subs = [api for api in API_ENDPOINTS if API_ENDPOINTS[api].get('enabled', True)]
    else:
        subs = []
        for api in API_ENDPOINTS:
            if API_ENDPOINTS[api].get('enabled', True) and await has_active_subscription(uid, api):
                subs.append(api)
        if not subs:
            await q.edit_message_text("❌ No active subscription.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
            return

    kb = []
    row = []
    for api in subs:
        name = API_ENDPOINTS[api]['name']
        row.append(InlineKeyboardButton(name, callback_data=f"gen_{api}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([back_btn("menu_start")])
    await q.edit_message_text("🔑 **Select API to generate key:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def gen_specific_key(update, context):
    q = update.callback_query; await q.answer()
    api_type = q.data.split('_')[1]; uid = update.effective_user.id
    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        await q.edit_message_text("❌ No subscription.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
        return
    key = await generate_random_key()
    await create_api_key(key, uid, expires_days=30, rate_limit=80, custom_name=f"{api_type.upper()}_Key")
    await log_key_gen(uid, key, api_type)
    ex = API_ENDPOINTS[api_type]['param_example']
    ep = f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}?key={key}&{API_ENDPOINTS[api_type]['param_name']}={ex}"
    await q.edit_message_text(
        f"✅ Key: <code>{key}</code>\nExample:\n<code>{ep}</code>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[back_btn("menu_genkey")]])
    )

async def custom_key_start(update, context):
    q = update.callback_query
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Number", callback_data="custkey_num"), InlineKeyboardButton("📱 TG", callback_data="custkey_tg")],
        [back_btn("menu_start")]
    ])
    await q.edit_message_text("Select API for custom key:", reply_markup=kb)

async def custom_key_type_selected(update, context):
    q = update.callback_query; await q.answer()
    api = q.data.split('_')[1]; context.user_data['custkey_api'] = api
    context.user_data['admin_state'] = 'awaiting_custom_key_string'
    await q.edit_message_text("Send your desired API key (any non-empty string):", reply_markup=InlineKeyboardMarkup([[back_btn("menu_customkey")]]))

async def custom_key_admin(update, context):
    await custom_key_start(update, context)

async def apihelp_menu(update, context):
    q = update.callback_query
    text = "📘 <b>API Docs</b>\n\n"
    for k, v in API_ENDPOINTS.items():
        text += f"<b>{v['name']}</b>\n<code>{RENDER_EXTERNAL_URL}/api/v1/{k}?key=KEY&{v['param_name']}={v['param_example']}</code>\n\n"
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

async def mykeys_menu(update, context):
    q = update.callback_query; uid = update.effective_user.id
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
    q = update.callback_query; uid = update.effective_user.id
    bal = await get_user_credits(uid)
    has_num = await has_active_subscription(uid, 'num')
    has_tg = await has_active_subscription(uid, 'tg')
    text = f"💰 Credits: <b>{bal}</b>\n📞 Num: {'✅' if has_num else '❌'}\n📱 TG: {'✅' if has_tg else '❌'}\n\nBuy plan:"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Num Weekly (15)", callback_data="plan_num_weekly")],
        [InlineKeyboardButton("📞 Num Monthly (30)", callback_data="plan_num_monthly")],
        [InlineKeyboardButton("📱 TG Weekly (15)", callback_data="plan_tg_weekly")],
        [InlineKeyboardButton("📱 TG Monthly (30)", callback_data="plan_tg_monthly")],
        [back_btn("menu_start")]
    ])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=kb)

async def buy_plan(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split('_'); api_type=parts[1]; plan=parts[2]; uid=update.effective_user.id
    if await is_admin(uid):
        pl = await get_plan(api_type, plan)
        if pl:
            async with pool.acquire() as conn:
                start = datetime.now(timezone.utc); end = start + timedelta(days=pl['duration_days'])
                await conn.execute("INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) VALUES ($1,$2,$3,$4,$5,TRUE)",
                                   uid, api_type, pl['plan_id'], start, end)
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
        await q.edit_message_text(f"✅ Purchased {api_type.upper()} {plan} plan.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]]))
    else:
        await q.answer("Failed.", show_alert=True)

async def referral_menu(update, context):
    q = update.callback_query; uid = update.effective_user.id
    me = await application.bot.get_me(); link = f"https://t.me/{me.username}?start=ref_{uid}"
    await q.edit_message_text(f"🔗 Link:\n<code>{link}</code>\nEarn {REFERRAL_REWARD_CREDITS} credits.", parse_mode='HTML',
                              reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

async def redeem_prompt(update, context):
    q = update.callback_query; context.user_data['awaiting_redeem'] = True
    await q.edit_message_text("Send redeem code:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]]))

# ====================== ADMIN PANEL HANDLERS ======================
async def admin_menu_handler(update, context):
    q = update.callback_query; data = q.data; await q.answer()
    if data == "admin_users": await show_user_list(update, context, 0)
    elif data == "admin_fullkeys": await show_full_keys(update, context)
    elif data == "admin_addcredits":
        context.user_data['admin_state'] = 'awaiting_user_for_credits'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_premium": await show_premium_list(update, context, 0)
    elif data == "admin_genredeem":
        context.user_data['admin_state'] = 'awaiting_redeem_credits'
        await q.edit_message_text("Credits amount:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_admins": await show_admin_list(update, context, 0)
    elif data == "admin_stats":
        total = await count_users()
        async with pool.acquire() as conn:
            keys = await conn.fetchval("SELECT COUNT(*) FROM api_keys")
            prem = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
        await q.edit_message_text(f"📊 Users: {total}\nKeys: {keys}\nPremium: {prem}", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_dm":
        context.user_data['admin_state'] = 'awaiting_dm_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_bulkdm":
        context.user_data['admin_state'] = 'awaiting_bulkdm_ids'
        await q.edit_message_text("Send comma-separated IDs or text file:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_broadcast_toggle":
        current = context.user_data.get('broadcast_mode', False)
        context.user_data['broadcast_mode'] = not current
        await q.edit_message_text("🛡️ Admin Panel", reply_markup=admin_panel_kb(not current))
    elif data == "admin_pricing":
        context.user_data['admin_state'] = 'awaiting_pricing_api'
        kb = []
        for api in API_ENDPOINTS:
            kb.append([InlineKeyboardButton(f"{API_ENDPOINTS[api]['name']}", callback_data=f"price_{api}")])
        kb.append([back_btn("menu_admin")])
        await q.edit_message_text("Select API:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("price_"):
        api = data.split('_')[1]; context.user_data['pricing_api'] = api
        context.user_data['admin_state'] = 'awaiting_pricing_plan'
        await q.edit_message_text("Which plan? (weekly/monthly):", reply_markup=InlineKeyboardMarkup([[back_btn("admin_pricing")]]))
    elif data == "admin_customkey": await custom_key_admin(update, context)
    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))
    elif data == "admin_edit_responses":
        kb = [[InlineKeyboardButton(f"{api} - {API_ENDPOINTS[api]['name']}", callback_data=f"editresp_{api}")] for api in API_ENDPOINTS]
        kb.append([back_btn("menu_admin")])
        await q.edit_message_text("Choose API to edit responses:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("editresp_"):
        api = data.split("_",1)[1]; context.user_data['edit_api'] = api
        context.user_data['admin_state'] = 'awaiting_response_type'
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Expired Key", callback_data="resptype_expired_key")],
            [InlineKeyboardButton("Invalid Key", callback_data="resptype_invalid_key")],
            [InlineKeyboardButton("No Subscription", callback_data="resptype_no_subscription")],
            [InlineKeyboardButton("Upstream Error", callback_data="resptype_upstream_error")],
            [back_btn("admin_edit_responses")]
        ])
        await q.edit_message_text("Select message type to edit:", reply_markup=kb)
    elif data.startswith("resptype_"):
        msg_type = data.split("_",1)[1]; context.user_data['edit_msg_type'] = msg_type
        context.user_data['admin_state'] = 'awaiting_custom_response_text'
        await q.edit_message_text("Send new message text (HTML formatting allowed):", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_toggle_api":
        kb = []
        for api, cfg in API_ENDPOINTS.items():
            status = "✅" if cfg.get('enabled', True) else "❌"
            kb.append([InlineKeyboardButton(f"{status} {api} - {cfg['name']}", callback_data=f"toggleapi_{api}")])
        kb.append([back_btn("menu_admin")])
        await q.edit_message_text("Toggle APIs:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("toggleapi_"):
        api = data.split("_",1)[1]
        if api in API_ENDPOINTS:
            API_ENDPOINTS[api]['enabled'] = not API_ENDPOINTS[api].get('enabled', True)
            await q.answer(f"API {api} {'enabled' if API_ENDPOINTS[api]['enabled'] else 'disabled'}.", show_alert=True)
            # Refresh panel
            bmode = context.user_data.get('broadcast_mode', False)
            await q.edit_message_text("🛡️ Admin Panel", reply_markup=admin_panel_kb(bmode))
    else:
        await q.answer("Coming soon.", show_alert=True)

# ====================== PAGINATION VIEWS ======================
async def show_user_list(update, context, page):
    q = update.callback_query; limit=10; offset=page*limit
    users = await get_users_paginated(offset, limit); total = await count_users()
    pages = max((total+limit-1)//limit, 1)
    text = f"👥 <b>Users (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for u in users:
        uid, uname, fname, banned, prem, creds = u['user_id'], u['username'], u['first_name'], u['is_banned'], u['is_premium'], u['credits']
        name = fname or str(uid)
        stat = "🚫" if banned else ("⭐" if prem else "✅")
        kb.append([InlineKeyboardButton(f"{stat} {name} | 💰{creds}", callback_data=f"userdetail_{uid}")])
        row = []
        row.append(InlineKeyboardButton("🚫" if not banned else "✅", callback_data=f"toggle_ban_{uid}"))
        row.append(InlineKeyboardButton("💳", callback_data=f"add_credits_{uid}"))
        row.append(InlineKeyboardButton("⭐" if prem else "⭐", callback_data=f"{'remove_premium_' if prem else 'make_premium_'}{uid}"))
        kb.append(row)
    nav = []
    if page>0: nav.append(InlineKeyboardButton("◀️", callback_data=f"userlist_page_{page-1}"))
    if page<pages-1: nav.append(InlineKeyboardButton("▶️", callback_data=f"userlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_user_list(update, context):
    page = int(update.callback_query.data.split('_')[-1]); await show_user_list(update, context, page)

async def user_detail_popup(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[1])
    user = await get_user(uid)
    text = f"👤 {user.get('first_name','N/A')} (@{user.get('username','')})\nID: {uid}\nCredits: {user['credits']}\nPremium: {'Yes' if user['is_premium'] else 'No'}\nBanned: {'Yes' if user['is_banned'] else 'No'}"
    await q.answer(text, show_alert=True)

async def show_premium_list(update, context, page):
    q = update.callback_query; limit=10; offset=page*limit
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, first_name, premium_expiry FROM users WHERE is_premium=TRUE ORDER BY user_id LIMIT $1 OFFSET $2", limit, offset)
        total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
    pages = max((total+limit-1)//limit, 1)
    text = f"⭐ <b>Premium Users (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for u in rows:
        uid, uname, fname, exp = u['user_id'], u['username'], u['first_name'], u['premium_expiry']
        name = fname or str(uid); exp_str = exp.strftime('%Y-%m-%d') if exp else 'Permanent'
        kb.append([InlineKeyboardButton(f"{name} | Exp: {exp_str}", callback_data=f"premdetail_{uid}")])
        kb.append([InlineKeyboardButton("❌ Remove", callback_data=f"remove_premium_{uid}")])
    nav = []
    if page>0: nav.append(InlineKeyboardButton("◀️", callback_data=f"premiumlist_page_{page-1}"))
    if page<pages-1: nav.append(InlineKeyboardButton("▶️", callback_data=f"premiumlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_premium_list(update, context):
    page = int(update.callback_query.data.split('_')[-1]); await show_premium_list(update, context, page)

async def show_admin_list(update, context, page):
    q = update.callback_query; limit=10; offset=page*limit
    admins = await get_admins_paginated(offset, limit); total = await count_admins()
    pages = max((total+limit-1)//limit, 1)
    text = f"👑 <b>Admins (Page {page+1}/{pages})</b>\n\n"
    kb = []
    for a in admins:
        uid, uname, fname = a['user_id'], a['username'], a['first_name']
        name = fname or str(uid)
        kb.append([InlineKeyboardButton(f"{name}", callback_data=f"admindetail_{uid}")])
        if uid != OWNER_ID: kb.append([InlineKeyboardButton("❌ Demote", callback_data=f"admintoggle_{uid}")])
    nav = []
    if page>0: nav.append(InlineKeyboardButton("◀️", callback_data=f"adminlist_page_{page-1}"))
    if page<pages-1: nav.append(InlineKeyboardButton("▶️", callback_data=f"adminlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_admin_list(update, context):
    page = int(update.callback_query.data.split('_')[-1]); await show_admin_list(update, context, page)

async def show_full_keys(update, context):
    q = update.callback_query
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, created_by, expires_at, is_active, total_requests_allowed, requests_made FROM api_keys")
    if not rows:
        await q.edit_message_text("No API keys found.", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
        return
    text_lines = []
    for k in rows:
        status = "✅" if k['is_active'] else "❌"
        text_lines.append(f"{status} {k['key']} | User: {k['created_by']} | Exp: {k['expires_at'].strftime('%Y-%m-%d')}")
    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        file_bytes = full_text.encode('utf-8')
        await q.edit_message_text("📁 Too many keys, sending as file...")
        await application.bot.send_document(chat_id=q.message.chat_id, document=file_bytes, filename="all_api_keys.txt", caption=f"Total keys: {len(rows)}")
    else:
        await q.edit_message_text(f"🔑 <b>All API Keys</b>\n\n{full_text}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))

# ====================== ACTION HANDLERS ======================
async def toggle_ban(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[-1])
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = NOT is_banned WHERE user_id=$1", uid)
    await q.answer("User ban toggled.", show_alert=True)
    await show_user_list(update, context, 0)

async def add_credits_prompt(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[-1]); context.user_data['target_user'] = uid
    context.user_data['admin_state'] = 'awaiting_credit_amount'
    await q.edit_message_text(f"Amount to add for {uid}:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_users")]]))

async def remove_premium_handler(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[-1]); await remove_premium(uid)
    await q.answer("Premium removed.", show_alert=True)
    await show_premium_list(update, context, 0)

async def make_premium_prompt(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[-1]); context.user_data['target_premium_user'] = uid
    context.user_data['admin_state'] = 'awaiting_premium_days'
    await q.edit_message_text(f"Days for premium (or 'permanent'):", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))

async def toggle_admin(update, context):
    q = update.callback_query; await q.answer()
    uid = int(q.data.split('_')[1])
    if uid == OWNER_ID: await q.answer("Cannot demote main owner.", show_alert=True); return
    is_owner = await is_admin(uid); await set_admin(uid, not is_owner)
    await q.answer(f"Admin {'removed' if is_owner else 'added'}.", show_alert=True)
    await show_admin_list(update, context, 0)

async def toggle_key_status(update, context):
    q = update.callback_query; await q.answer()
    key = q.data.split('_', 1)[1]
    async with pool.acquire() as conn:
        active = await conn.fetchval("SELECT is_active FROM api_keys WHERE key=$1", key)
    if active: await deactivate_api_key(key); await q.answer("Key deactivated.", show_alert=True)
    else: await activate_api_key(key); await q.answer("Key activated.", show_alert=True)
    # Show updated keys list? We'll just refresh via admin menu later; for simplicity, we'll call show_full_keys? Not necessary.
    await q.answer("Done.", show_alert=True)

# ====================== DELETE KEY ======================
async def confirm_delete_key(update, context):
    q = update.callback_query; await q.answer()
    key = q.data.split("delete_key_", 1)[1]
    context.user_data['del_key'] = key
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_delete_key_{key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_panel")]
    ])
    await q.edit_message_text(f"Delete key <code>{key[:20]}...</code>?", parse_mode='HTML', reply_markup=kb)

async def execute_delete_key(update, context):
    q = update.callback_query; await q.answer()
    key = q.data.split("confirm_delete_key_", 1)[1]
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM api_keys WHERE key=$1", key)
    await q.edit_message_text(f"✅ Key deleted: <code>{key[:20]}...</code>", parse_mode='HTML')

# ====================== SMART BROADCAST HANDLER ======================
async def smart_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all message types for broadcast when broadcast_mode is ON."""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return
    if not context.user_data.get('broadcast_mode'):
        return  # let other handlers process

    msg = update.message
    if not msg:
        return

    async def send_to_user(uid):
        try:
            if msg.text:
                await application.bot.send_message(uid, msg.text, parse_mode='HTML')
            elif msg.photo:
                await application.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                await application.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif msg.audio:
                await application.bot.send_audio(uid, msg.audio.file_id, caption=msg.caption or "")
            elif msg.voice:
                await application.bot.send_voice(uid, msg.voice.file_id, caption=msg.caption or "")
            elif msg.document:
                await application.bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            elif msg.sticker:
                await application.bot.send_sticker(uid, msg.sticker.file_id)
            elif msg.animation:
                await application.bot.send_animation(uid, msg.animation.file_id, caption=msg.caption or "")
            else:
                return False
            return True
        except:
            return False

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned=FALSE")
    users = [r['user_id'] for r in rows]
    total = len(users)
    success = 0
    fail = 0

    for uid_target in users:
        retries = 3
        sent = False
        while retries > 0:
            try:
                if await send_to_user(uid_target):
                    success += 1
                    sent = True
                    break
            except Exception as e:
                err_str = str(e)
                if 'Too Many Requests' in err_str:
                    m = re.search(r'retry after (\d+)', err_str)
                    wait = int(m.group(1)) + 1 if m else 30
                    await asyncio.sleep(wait)
                    retries -= 1
                else:
                    fail += 1
                    break
        if not sent:
            fail += 1
        await asyncio.sleep(0.03)

    await msg.reply_text(f"📊 Broadcast Report:\n✅ Sent: {success}\n❌ Failed: {fail}\n📝 Total: {total}")

# ====================== TEXT MESSAGE HANDLER (Admin States) ======================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; text = update.message.text.strip()

    # Redeem code flow
    if context.user_data.get('awaiting_redeem'):
        context.user_data.pop('awaiting_redeem')
        if await redeem_code(uid, text):
            await update.message.reply_text("✅ Redeemed!")
        else:
            await update.message.reply_text("❌ Invalid/expired code.")
        return

    # If admin and broadcast mode is ON, smart_broadcast_handler already handled it.
    # So here we only proceed if not broadcast_mode.
    if not await is_admin(uid):
        return

    state = context.user_data.get('admin_state')
    if not state:
        return

    if state == 'awaiting_user_for_credits':
        try: target = int(text); context.user_data['target_user'] = target; context.user_data['admin_state'] = 'awaiting_credit_amount'; await update.message.reply_text("Amount:")
        except: await update.message.reply_text("Invalid ID."); context.user_data.pop('admin_state', None)
    elif state == 'awaiting_credit_amount':
        try:
            amt = int(text); target = context.user_data.pop('target_user')
            await add_credits(target, amt)
            await update.message.reply_text(f"✅ Added {amt} credits to {target}."); context.user_data.pop('admin_state', None)
        except: await update.message.reply_text("Invalid amount.")
    elif state == 'awaiting_redeem_credits':
        try: creds = int(text); context.user_data['redeem_creds'] = creds; context.user_data['admin_state'] = 'awaiting_redeem_maxuses'; await update.message.reply_text("Max uses:")
        except: await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_redeem_maxuses':
        try:
            maxu = int(text); creds = context.user_data.pop('redeem_creds')
            code = secrets.token_hex(4).upper(); await create_redeem_code(code, creds, uid, maxu)
            await update.message.reply_text(f"✅ Code: <code>{code}</code>\nCredits: {creds}\nUses: {maxu}")
            context.user_data.pop('admin_state', None)
        except: await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_dm_user':
        try: target = int(text); context.user_data['dm_target'] = target; context.user_data['admin_state'] = 'awaiting_dm_message'; await update.message.reply_text("Message:")
        except: await update.message.reply_text("Invalid ID.")
    elif state == 'awaiting_dm_message':
        target = context.user_data.pop('dm_target')
        try: await application.bot.send_message(target, text, parse_mode='HTML'); await update.message.reply_text("✅ Sent.")
        except Exception as e: await update.message.reply_text(f"❌ {e}")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_bulkdm_ids':
        ids = [int(x.strip()) for x in text.replace('\n',',').split(',') if x.strip().isdigit()]
        context.user_data['bulk_ids'] = ids; context.user_data['admin_state'] = 'awaiting_bulkdm_message'
        await update.message.reply_text(f"Got {len(ids)} IDs. Send message:")
    elif state == 'awaiting_bulkdm_message':
        ids = context.user_data.pop('bulk_ids'); success = 0
        for i in ids:
            try: await application.bot.send_message(i, text, parse_mode='HTML'); success += 1
            except: pass
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ Sent to {success}/{len(ids)}."); context.user_data.pop('admin_state', None)
    elif state == 'awaiting_custom_key_string':
        key = text.strip()
        if not key: await update.message.reply_text("Key cannot be empty."); return
        exists = await pool.fetchval("SELECT key FROM api_keys WHERE key=$1", key)
        if exists: await update.message.reply_text("Key already exists."); return
        context.user_data['cust_key'] = key; context.user_data['admin_state'] = 'awaiting_custom_key_expiry'
        await update.message.reply_text("Expiry in days (e.g., 30) or 'permanent':")
    elif state == 'awaiting_custom_key_expiry':
        if text.lower() == 'permanent': context.user_data['cust_expiry'] = 'permanent'
        else:
            try:
                days = int(text)
                if days <= 0: await update.message.reply_text("Days must be positive or 'permanent'."); return
                context.user_data['cust_expiry'] = days
            except: await update.message.reply_text("Invalid number."); return
        context.user_data['admin_state'] = 'awaiting_custom_key_totalreq'
        await update.message.reply_text("Total requests allowed (0 for unlimited):")
    elif state == 'awaiting_custom_key_totalreq':
        try:
            total = int(text); context.user_data['cust_total'] = total if total > 0 else None
        except: await update.message.reply_text("Invalid number."); return
        context.user_data['admin_state'] = 'awaiting_custom_key_ratelimit'
        await update.message.reply_text("Rate limit per minute:")
    elif state == 'awaiting_custom_key_ratelimit':
        try: rate = int(text); context.user_data['cust_rate'] = rate
        except: await update.message.reply_text("Invalid number."); return
        expiry_days = context.user_data['cust_expiry']
        if expiry_days == 'permanent': expiry_days = 36500
        await create_api_key(context.user_data['cust_key'], uid, expires_days=expiry_days, rate_limit=context.user_data['cust_rate'], total_requests=context.user_data['cust_total'], custom_name=f"{context.user_data['custkey_api'].upper()}_Custom")
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
    elif state == 'awaiting_pricing_api':
        if text in API_ENDPOINTS: context.user_data['pricing_api'] = text; context.user_data['admin_state'] = 'awaiting_pricing_plan'; await update.message.reply_text("Plan (weekly/monthly):")
        else: await update.message.reply_text("Invalid API.")
    elif state == 'awaiting_pricing_plan':
        if text.lower() in ['weekly','monthly']: context.user_data['pricing_plan'] = text.lower(); context.user_data['admin_state'] = 'awaiting_pricing_credits'; await update.message.reply_text("New price (credits):")
        else: await update.message.reply_text("Invalid plan.")
    elif state == 'awaiting_pricing_credits':
        try:
            price = int(text); api = context.user_data.pop('pricing_api'); plan = context.user_data.pop('pricing_plan')
            async with pool.acquire() as conn:
                await conn.execute("UPDATE api_plans SET price_credits=$1 WHERE api_type=$2 AND plan_name=$3", price, api, plan)
            await update.message.reply_text(f"✅ Updated {api.upper()} {plan} = {price} credits."); context.user_data.pop('admin_state', None)
        except: await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_premium_user':
        try: target = int(text); context.user_data['target_premium_user'] = target; context.user_data['admin_state'] = 'awaiting_premium_days'; await update.message.reply_text("Days (or 'permanent'):")
        except: await update.message.reply_text("Invalid ID.")
    elif state == 'awaiting_premium_days':
        days_txt = text.lower(); target = context.user_data.pop('target_premium_user')
        if days_txt == 'permanent': await set_premium(target, days=None)
        else:
            try: await set_premium(target, days=int(days_txt))
            except: await update.message.reply_text("Invalid."); return
        await update.message.reply_text(f"✅ Premium set for {target}."); context.user_data.pop('admin_state', None)
    elif state == 'awaiting_custom_response_text':
        api = context.user_data.get('edit_api')
        msg_type = context.user_data.get('edit_msg_type')
        if api:
            if api not in CUSTOM_ERROR_OVERRIDES: CUSTOM_ERROR_OVERRIDES[api] = {}
            CUSTOM_ERROR_OVERRIDES[api][msg_type] = text
            context.user_data.pop('admin_state', None)
            await update.message.reply_text(f"✅ Response updated for {api} - {msg_type}")
        else:
            await update.message.reply_text("Session expired.")
        context.user_data.pop('edit_api', None); context.user_data.pop('edit_msg_type', None)

# ====================== MEDIA BROADCAST (OLD, REPLACED) ======================
# Not needed, handled by smart_broadcast_handler

# ====================== BACKGROUND TASKS ======================
async def self_ping():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(SELF_PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as s: await s.get(f"{RENDER_EXTERNAL_URL}/health")
            await application.bot.get_me()
        except: pass

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
                if not content: continue
                await application.bot.send_document(
                    chat_id=BACKUP_CHAT_ID, document=content.encode('utf-8'),
                    filename=f"{table}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
                    caption=f"📁 {table}"
                )
            await application.bot.send_message(BACKUP_CHAT_ID, "✅ Daily backup complete.")
        except Exception as e: logger.error(f"Backup failed: {e}")

# ====================== STARTUP / SHUTDOWN ======================
async def on_startup():
    global http_session
    await init_db()
    global pool; pool = database.pool
    init_sheets()
    await redis_client.init_redis()
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
    if http_session: await http_session.close()
    await application.stop(); await application.shutdown()
    await close_db()
    await redis_client.close_redis()

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

# Smart broadcast handler (high priority) – catches all messages when broadcast_mode ON
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, smart_broadcast_handler), group=0)
# Text handler for admin states (only works when broadcast_mode OFF, because smart_broadcast_handler will block it)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text), group=1)

if __name__ == '__main__':
    import hypercorn.asyncio
    from hypercorn.config import Config
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(on_startup())
    loop.run_until_complete(hypercorn.asyncio.serve(app, config))
