# main.py - UPGRADED PRODUCTION VERSION
# Bug fixes + 19 APIs + Category menus + Google Sheets (All Logs)

import json, asyncio, secrets, time, re, aiohttp, logging, os
from datetime import datetime, timedelta, timezone
from quart import Quart, request, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import (
    TELEGRAM_BOT_TOKEN, OWNER_ID, WEBHOOK_SECRET, BOT_MODE,
    RENDER_EXTERNAL_URL, PORT, LOG_CHANNEL_ID,
    FORCE_JOIN_CHANNELS, PREMIUM_EXEMPT_FORCE_JOIN,
    BRANDING, GLOBAL_BLACKLIST, REFERRAL_REWARD_CREDITS,
    BACKUP_INTERVAL_HOURS, BACKUP_CHAT_ID, SELF_PING_INTERVAL,
    ENABLE_SELF_PING, LOG_LEVEL, IP_API_URL,
    API_ENDPOINTS, API_CATEGORIES, DEFAULT_PLANS
)
from database import (
    pool, init_db, get_user, update_user_info, set_referrer,
    add_credits, deduct_credits, get_user_credits,
    is_admin, is_premium, set_premium, remove_premium, set_admin, ban_user,
    generate_random_key, create_api_key, validate_api_key, list_api_keys,
    deactivate_api_key, activate_api_key, get_request_stats, increment_request_count,
    key_exists,
    get_plan, create_subscription, has_active_subscription,
    create_redeem_code, redeem_code,
    count_users, get_users_paginated, count_admins, get_admins_paginated,
    export_tables_to_csv, close_db,
)
import database
from sheets import init_sheets, log_api_call

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

app         = Quart(__name__)
cache: dict = {}
http_session: aiohttp.ClientSession = None
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def remove_branding(data, extra_blacklist=None):
    if extra_blacklist is None:
        extra_blacklist = []
    blacklist = set(
        [t.lower() for t in GLOBAL_BLACKLIST] +
        [t.lower() for t in extra_blacklist]
    )
    if isinstance(data, str):   return data
    if isinstance(data, list):
        cleaned = [remove_branding(i, extra_blacklist) for i in data]
        return [x for x in cleaned if x not in ("", None)]
    if isinstance(data, dict):
        return {
            k: v2
            for k, v in data.items()
            if k.lower() not in blacklist
            for v2 in [remove_branding(v, extra_blacklist)]
            if v2 not in ("", None)
        }
    return data

async def get_cached(key):
    if key in cache and time.time() - cache[key][0] < 300:
        return cache[key][1]
    return None

async def set_cached(key, data):
    cache[key] = (time.time(), data)


# ══════════════════════════════════════════════════════════════
#  QUART ROUTES
# ══════════════════════════════════════════════════════════════

@app.route('/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@app.route('/api/v1/<api_type>')
async def proxy_api(api_type):
    if api_type not in API_ENDPOINTS:
        return jsonify({"error": "Invalid API type"}), 400

    cfg = API_ENDPOINTS[api_type]
    if not cfg.get("enabled", True):
        return jsonify({"error": "API disabled"}), 503

    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    valid, uid, rate_limit = await validate_api_key(key)
    if not valid:
        return jsonify({"error": "Invalid or expired API key"}), 403

    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        return jsonify({"error": "No active subscription for this API"}), 403

    # ── Rate limiting ────────────────────────────────────────
    rate_key = f"rate_{key}"
    now      = time.time()
    if rate_key in cache:
        count, start = cache[rate_key]
        if now - start > 60:
            cache[rate_key] = (1, now)
        elif count >= rate_limit:
            return jsonify({"error": "Rate limit exceeded"}), 429
        else:
            cache[rate_key] = (count + 1, start)
    else:
        cache[rate_key] = (1, now)

    # ── Request quota ────────────────────────────────────────
    used, remaining, total = await get_request_stats(key)
    if total is not None and used is not None and used >= total:
        return jsonify({"error": "Request quota exhausted"}), 429

    # ── Parameter validation ─────────────────────────────────
    param_name  = cfg['param_name']
    param_value = request.args.get(param_name)
    if not param_value:
        return jsonify({"error": f"Missing '{param_name}' parameter"}), 400
    if 'param_validation' in cfg and not re.match(cfg['param_validation'], param_value, re.IGNORECASE):
        return jsonify({"error": f"Invalid {param_name} format"}), 400

    # ── Cache check ──────────────────────────────────────────
    cache_key = f"api_{api_type}_{param_value}"
    cached    = await get_cached(cache_key)
    if cached:
        await increment_request_count(key)
        return app.response_class(response=cached, status=200, mimetype='application/json')

    # ── Upstream call ────────────────────────────────────────
    url = cfg['url_template'].format(api_key=cfg['external_api_key'], param=param_value)
    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return jsonify({"error": f"Upstream returned {resp.status}"}), 502
            data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        return jsonify({"error": "Upstream API timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    cleaned = remove_branding(data, cfg.get('extra_blacklist', []))

    # ── IP lookup + Sheets logging (background) ──────────────
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or "")
    if ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    async def background_log():
        try:
            ip_info = {"ip": client_ip}
            if client_ip and not client_ip.startswith(("127.", "10.", "192.168.")):
                try:
                    ip_url = IP_API_URL.format(client_ip)
                    async with http_session.get(ip_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                        if r.status == 200:
                            ip_info = await r.json()
                except Exception as e:
                    logger.warning(f"IP lookup failed: {e}")

            await log_api_call(
                api_type    = api_type,
                api_name    = cfg['name'],
                api_key     = key,
                input_value = param_value,
                client_ip   = client_ip,
                ip_info     = ip_info,
                response_data = cleaned,
            )
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
        data   = await request.get_json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════

def main_menu(is_admin_flag, is_prem):
    btns = [
        [InlineKeyboardButton("🔑 Generate Key",     callback_data="menu_genkey"),
         InlineKeyboardButton("📘 API Docs",          callback_data="menu_apihelp")],
        [InlineKeyboardButton("👤 My Keys",           callback_data="menu_mykeys"),
         InlineKeyboardButton("💰 Balance & Plans",   callback_data="menu_balance")],
        [InlineKeyboardButton("🔗 Referral",          callback_data="menu_referral"),
         InlineKeyboardButton("🎟️ Redeem Code",       callback_data="menu_redeem")],
    ]
    if is_admin_flag or is_prem:
        btns.append([InlineKeyboardButton("🎨 Custom Key", callback_data="menu_customkey")])
    if is_admin_flag:
        btns.append([InlineKeyboardButton("🛡️ Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(btns)

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users",      callback_data="admin_users"),
         InlineKeyboardButton("📢 Broadcast",  callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔑 All Keys",   callback_data="admin_keys"),
         InlineKeyboardButton("💳 Add Credits",callback_data="admin_addcredits")],
        [InlineKeyboardButton("⭐ Premium",    callback_data="admin_premium"),
         InlineKeyboardButton("🎟️ Redeem",     callback_data="admin_genredeem")],
        [InlineKeyboardButton("👑 Admins",     callback_data="admin_admins"),
         InlineKeyboardButton("📊 Stats",      callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Pricing",    callback_data="admin_pricing"),
         InlineKeyboardButton("📨 DM",         callback_data="admin_dm")],
        [InlineKeyboardButton("📨 Bulk DM",    callback_data="admin_bulkdm"),
         InlineKeyboardButton("🎨 Custom Key", callback_data="admin_customkey")],
        [InlineKeyboardButton("❌ Close",       callback_data="close_panel")],
    ])

back_btn = lambda data: InlineKeyboardButton("🔙 Back", callback_data=data)

def category_menu_kb(user_categories):
    """Keyboard showing only categories the user has subscriptions for."""
    kb = []
    for cat_key, cat_label in API_CATEGORIES.items():
        kb.append([InlineKeyboardButton(cat_label, callback_data=f"cat_{cat_key}")])
    kb.append([back_btn("menu_start")])
    return InlineKeyboardMarkup(kb)

def apis_in_category_kb(category, back="menu_genkey"):
    """Keyboard listing all APIs in a category."""
    apis = [(k, v) for k, v in API_ENDPOINTS.items() if v.get("category") == category and v.get("enabled")]
    kb   = [[InlineKeyboardButton(v['name'], callback_data=f"gen_{k}")] for k, v in apis]
    kb.append([back_btn(back)])
    return InlineKeyboardMarkup(kb)


# ══════════════════════════════════════════════════════════════
#  FORCE JOIN
# ══════════════════════════════════════════════════════════════

async def check_force_join(user_id):
    if await is_admin(user_id): return True, []
    if PREMIUM_EXEMPT_FORCE_JOIN and await is_premium(user_id): return True, []
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
    kb   = [[InlineKeyboardButton(f"Join {ch['name']}", url=ch['link'])] for ch in missing]
    kb.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    await application.bot.send_message(
        chat_id, text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb)
    )


# ══════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = user.id
    await update_user_info(uid, user.username, user.first_name, user.last_name)

    # Referral
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

    async with database.pool.acquire() as conn:
        await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)

    if 'pending_ref' in context.user_data:
        ref = context.user_data.pop('pending_ref')
        await add_credits(ref, REFERRAL_REWARD_CREDITS)
        try:
            await application.bot.send_message(ref, f"🎉 +{REFERRAL_REWARD_CREDITS} credits — referral bonus!")
        except:
            pass

    is_adm  = await is_admin(uid)
    is_prem = await is_premium(uid)
    await update.message.reply_text(
        f"✨ Welcome, <b>{user.first_name}</b>!", parse_mode='HTML',
        reply_markup=main_menu(is_adm, is_prem)
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = await get_user_credits(uid)
    await update.message.reply_text(
        f"💰 Credits: <b>{bal}</b>\n\nBuy a plan to access any API:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Browse Plans", callback_data="menu_balance")],
        ])
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await balance_command(update, context)

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_redeem'] = True
    await update.message.reply_text(
        "Send redeem code:",
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    me  = await application.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await update.message.reply_text(
        f"🔗 Your referral link:\n<code>{link}</code>\n\nEarn <b>{REFERRAL_REWARD_CREDITS}</b> credits per referral.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await is_admin(uid):
        await update.message.reply_text("🛡️ Admin Panel", reply_markup=admin_panel_kb())
    else:
        await update.message.reply_text("⛔ Access denied.")


# ══════════════════════════════════════════════════════════════
#  CHECK JOIN CALLBACK  (standalone — no duplicate)
# ══════════════════════════════════════════════════════════════

async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    joined, missing = await check_force_join(uid)
    if joined:
        async with database.pool.acquire() as conn:
            await conn.execute("UPDATE users SET joined_force_channels=TRUE WHERE user_id=$1", uid)
        await q.edit_message_text("✅ Thank you! Press /start to see the menu.")
    else:
        await q.answer("Please join all channels first!", show_alert=True)


# ══════════════════════════════════════════════════════════════
#  MAIN CALLBACK ROUTER
# ══════════════════════════════════════════════════════════════

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    uid  = update.effective_user.id
    is_adm  = await is_admin(uid)
    is_prem = await is_premium(uid)

    # Force join check (except close/check_join)
    if data not in ["close_panel"] and not data.startswith("check_join"):
        if not is_adm:
            joined, missing = await check_force_join(uid)
            if not joined:
                await q.edit_message_text(
                    "⚠️ Join all channels first.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Check Again", callback_data="check_join")]
                    ])
                )
                return

    # ── Navigation ───────────────────────────────────────────
    if data == "menu_start":
        await q.edit_message_text(
            f"✨ Welcome, <b>{update.effective_user.first_name}</b>!",
            parse_mode='HTML', reply_markup=main_menu(is_adm, is_prem)
        )
    elif data == "menu_genkey":   await genkey_category_menu(update, context)
    elif data == "menu_apihelp":  await apihelp_menu(update, context)
    elif data == "menu_mykeys":   await mykeys_menu(update, context)
    elif data == "menu_balance":  await balance_menu(update, context)
    elif data == "menu_referral": await referral_menu(update, context)
    elif data == "menu_redeem":   await redeem_prompt(update, context)
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
    elif data == "close_panel":
        await q.delete_message()

    # ── Category / API generation ────────────────────────────
    elif data.startswith("cat_"):
        cat = data[4:]
        await q.edit_message_text(
            f"Select API in {API_CATEGORIES.get(cat, cat)}:",
            reply_markup=apis_in_category_kb(cat)
        )
    elif data.startswith("gen_"):
        await gen_specific_key(update, context)

    # ── Plans ────────────────────────────────────────────────
    elif data.startswith("plan_"):
        await buy_plan(update, context)

    # ── Custom key ───────────────────────────────────────────
    elif data.startswith("custkey_"):
        await custom_key_type_selected(update, context)

    # ── Pagination ───────────────────────────────────────────
    elif data.startswith("userlist_page_"):     await paginated_user_list(update, context)
    elif data.startswith("premiumlist_page_"):  await paginated_premium_list(update, context)
    elif data.startswith("adminlist_page_"):    await paginated_admin_list(update, context)
    elif data.startswith("keys_page_"):         await paginated_keys_list(update, context)

    # ── User actions ─────────────────────────────────────────
    elif data.startswith("toggle_ban_"):        await toggle_ban(update, context)
    elif data.startswith("add_credits_"):       await add_credits_prompt(update, context)
    elif data.startswith("remove_premium_"):    await remove_premium_handler(update, context)
    elif data.startswith("make_premium_"):      await make_premium_prompt(update, context)
    elif data.startswith("userdetail_"):        await user_detail_popup(update, context)
    elif data.startswith("admintoggle_"):       await toggle_admin(update, context)
    elif data.startswith("keytoggle_"):         await toggle_key_status(update, context)
    elif data.startswith("delete_key_") and not data.startswith("confirm_delete_key_"):
        await confirm_delete_key(update, context)
    elif data.startswith("confirm_delete_key_"):await execute_delete_key(update, context)
    elif data.startswith("bcast_"):             await broadcast_type(update, context)

    # ── Admin sub-menus ──────────────────────────────────────
    elif data.startswith("admin_"):
        await admin_menu_handler(update, context)

    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text(
            "Send user ID to grant premium:",
            reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]])
        )
    else:
        await q.answer("Not implemented.", show_alert=True)


# ══════════════════════════════════════════════════════════════
#  SUB MENUS
# ══════════════════════════════════════════════════════════════

async def genkey_category_menu(update, context):
    """Show API categories instead of a flat list."""
    q   = update.callback_query
    uid = update.effective_user.id
    is_adm = await is_admin(uid)
    if not is_adm:
        # Check if user has at least one active subscription
        has_any = any(
            [await has_active_subscription(uid, k) for k in API_ENDPOINTS]
        )
        if not has_any:
            await q.edit_message_text(
                "❌ No active subscription.\n\nBuy a plan first:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Buy Plan", callback_data="menu_balance")],
                    [back_btn("menu_start")]
                ])
            )
            return
    await q.edit_message_text("Select API category:", reply_markup=category_menu_kb(None))

async def gen_specific_key(update, context):
    q        = update.callback_query
    await q.answer()
    api_type = q.data.split('_', 1)[1]
    uid      = update.effective_user.id

    if api_type not in API_ENDPOINTS:
        await q.answer("Unknown API.", show_alert=True)
        return

    if not await is_admin(uid) and not await has_active_subscription(uid, api_type):
        await q.edit_message_text(
            f"❌ No subscription for {API_ENDPOINTS[api_type]['name']}.",
            reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]])
        )
        return

    key = await generate_random_key()
    await create_api_key(key, uid, expires_days=30, rate_limit=80,
                         custom_name=f"{api_type.upper()}_Key")
    await log_key_gen(uid, key, api_type)

    cfg = API_ENDPOINTS[api_type]
    ep  = (f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}"
           f"?key={key}&{cfg['param_name']}={cfg['param_example']}")
    await q.edit_message_text(
        f"✅ <b>Key Generated!</b>\n\n"
        f"🔑 <code>{key}</code>\n\n"
        f"📡 API: {cfg['name']}\n"
        f"📎 Example:\n<code>{ep}</code>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_genkey")]])
    )

async def apihelp_menu(update, context):
    q    = update.callback_query
    text = "📘 <b>API Documentation</b>\n\n"
    for cat_key, cat_label in API_CATEGORIES.items():
        text += f"\n<b>{cat_label}</b>\n"
        for k, v in API_ENDPOINTS.items():
            if v.get("category") == cat_key and v.get("enabled"):
                text += (
                    f"  • {v['name']}\n"
                    f"    <code>{RENDER_EXTERNAL_URL}/api/v1/{k}"
                    f"?key=YOUR_KEY&{v['param_name']}={v['param_example']}</code>\n"
                )
    await q.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def mykeys_menu(update, context):
    q   = update.callback_query
    uid = update.effective_user.id
    keys = await list_api_keys(uid)
    text = "🔑 <b>Your Keys</b>\n\n"
    kb   = []
    if not keys:
        text += "No keys found."
    else:
        for row in keys:
            status   = "✅" if row['is_active'] else "❌"
            total_r  = row['total_requests_allowed']
            used_r   = row['requests_made']
            req_info = f" | Req: {max(0,total_r-used_r)}/{total_r}" if total_r else " | Req: ∞"
            exp_str  = row['expires_at'].strftime('%Y-%m-%d')
            text += f"{status} <code>{row['key'][:24]}...</code> Exp:{exp_str}{req_info}\n"
            kb.append([InlineKeyboardButton(
                f"🗑 Delete {row['key'][:10]}...", callback_data=f"delete_key_{row['key']}"
            )])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def balance_menu(update, context):
    q   = update.callback_query
    uid = update.effective_user.id
    bal = await get_user_credits(uid)

    # Build category-wise plan buttons
    text = f"💰 Credits: <b>{bal}</b>\n\n<b>Available Plans (15cr/week • 30cr/month):</b>\n"
    kb   = []
    for cat_key, cat_label in API_CATEGORIES.items():
        apis = [(k, v) for k, v in API_ENDPOINTS.items()
                if v.get("category") == cat_key and v.get("enabled")]
        if not apis:
            continue
        text += f"\n{cat_label}\n"
        for api_key, api_val in apis:
            has_sub = await has_active_subscription(uid, api_key)
            status  = "✅" if has_sub else "—"
            text   += f"  {status} {api_val['name']}\n"
            if not has_sub:
                kb.append([
                    InlineKeyboardButton(
                        f"📅 {api_val['name']} Weekly (15cr)",
                        callback_data=f"plan_{api_key}_weekly"
                    ),
                    InlineKeyboardButton(
                        f"📆 Monthly (30cr)",
                        callback_data=f"plan_{api_key}_monthly"
                    ),
                ])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def buy_plan(update, context):
    q     = update.callback_query
    await q.answer()
    parts    = q.data.split('_')   # plan_<api>_<planname>
    # api_type may contain underscore (e.g. vehicle2num) → handle carefully
    api_type = '_'.join(parts[1:-1])
    plan     = parts[-1]
    uid      = update.effective_user.id

    if api_type not in API_ENDPOINTS:
        await q.answer("Unknown API.", show_alert=True)
        return

    if await is_admin(uid):
        pl = await get_plan(api_type, plan)
        if pl:
            from datetime import timedelta
            start = datetime.now(timezone.utc)
            end   = start + timedelta(days=pl['duration_days'])
            async with database.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) "
                    "VALUES ($1,$2,$3,$4,$5,TRUE)",
                    uid, api_type, pl['plan_id'], start, end
                )
            await q.edit_message_text(
                "✅ Admin plan activated.",
                reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]])
            )
        else:
            await q.answer("Plan not found.", show_alert=True)
        return

    pl = await get_plan(api_type, plan)
    if not pl:
        await q.answer("Plan not found.", show_alert=True)
        return

    bal = await get_user_credits(uid)
    if bal < pl['price_credits']:
        await q.answer(f"Need {pl['price_credits']} credits. You have {bal}.", show_alert=True)
        return

    if await create_subscription(uid, api_type, plan):
        await q.edit_message_text(
            f"✅ Purchased <b>{API_ENDPOINTS[api_type]['name']}</b> {plan} plan!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[back_btn("menu_balance")]])
        )
    else:
        await q.answer("Purchase failed.", show_alert=True)

async def referral_menu(update, context):
    q   = update.callback_query
    uid = update.effective_user.id
    me  = await application.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await q.edit_message_text(
        f"🔗 Referral Link:\n<code>{link}</code>\n\nEarn <b>{REFERRAL_REWARD_CREDITS}</b> credits per referral.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def redeem_prompt(update, context):
    q = update.callback_query
    context.user_data['awaiting_redeem'] = True
    await q.edit_message_text(
        "Send your redeem code:",
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_start")]])
    )

async def custom_key_start(update, context):
    q  = update.callback_query
    kb = []
    for cat_key, cat_label in API_CATEGORIES.items():
        apis = [(k, v) for k, v in API_ENDPOINTS.items()
                if v.get("category") == cat_key and v.get("enabled")]
        for api_key, api_val in apis:
            kb.append([InlineKeyboardButton(api_val['name'], callback_data=f"custkey_{api_key}")])
    kb.append([back_btn("menu_start")])
    await q.edit_message_text("Select API for custom key:", reply_markup=InlineKeyboardMarkup(kb))

async def custom_key_type_selected(update, context):
    q    = update.callback_query
    await q.answer()
    api  = q.data[8:]   # strip "custkey_"
    if api not in API_ENDPOINTS:
        await q.answer("Unknown API.", show_alert=True)
        return
    context.user_data['custkey_api']    = api
    context.user_data['admin_state']    = 'awaiting_custom_key_string'
    await q.edit_message_text(
        "Send your desired API key string (any non-empty value):",
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_customkey")]])
    )

async def custom_key_admin(update, context):
    await custom_key_start(update, context)


# ══════════════════════════════════════════════════════════════
#  ADMIN PANEL HANDLERS
# ══════════════════════════════════════════════════════════════

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    if data == "admin_users":      await show_user_list(update, context, 0)
    elif data == "admin_keys":     await show_keys_list(update, context, 0)
    elif data == "admin_addcredits":
        context.user_data['admin_state'] = 'awaiting_user_for_credits'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_premium":  await show_premium_list(update, context, 0)
    elif data == "admin_genredeem":
        context.user_data['admin_state'] = 'awaiting_redeem_credits'
        await q.edit_message_text("Credits amount for redeem code:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_admins":   await show_admin_list(update, context, 0)
    elif data == "admin_stats":
        total = await count_users()
        async with database.pool.acquire() as conn:
            keys = await conn.fetchval("SELECT COUNT(*) FROM api_keys")
            prem = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
            subs = await conn.fetchval("SELECT COUNT(*) FROM user_subscriptions WHERE is_active=TRUE")
        await q.edit_message_text(
            f"📊 <b>Stats</b>\n\n"
            f"👥 Users: <b>{total}</b>\n"
            f"🔑 Keys: <b>{keys}</b>\n"
            f"⭐ Premium: <b>{prem}</b>\n"
            f"📋 Active Subs: <b>{subs}</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]])
        )
    elif data == "admin_dm":
        context.user_data['admin_state'] = 'awaiting_dm_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_bulkdm":
        context.user_data['admin_state'] = 'awaiting_bulkdm_ids'
        await q.edit_message_text("Send comma-separated user IDs:", reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]]))
    elif data == "admin_broadcast":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Text",     callback_data="bcast_text")],
            [InlineKeyboardButton("Photo",    callback_data="bcast_photo")],
            [InlineKeyboardButton("Video",    callback_data="bcast_video")],
            [InlineKeyboardButton("Document", callback_data="bcast_doc")],
            [back_btn("menu_admin")]
        ])
        await q.edit_message_text("Select broadcast type:", reply_markup=kb)
    elif data == "admin_pricing":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(v['name'], callback_data=f"price_{k}")]
            for k, v in API_ENDPOINTS.items() if v.get("enabled")
        ] + [[back_btn("menu_admin")]])
        await q.edit_message_text("Select API to update pricing:", reply_markup=kb)
    elif data.startswith("price_"):
        api = data[6:]
        context.user_data['pricing_api']   = api
        context.user_data['admin_state']   = 'awaiting_pricing_plan'
        await q.edit_message_text(
            f"Plan for {API_ENDPOINTS.get(api,{}).get('name', api)}?\nSend: weekly or monthly",
            reply_markup=InlineKeyboardMarkup([[back_btn("admin_pricing")]])
        )
    elif data == "admin_customkey": await custom_key_admin(update, context)
    elif data == "admin_addpremium":
        context.user_data['admin_state'] = 'awaiting_premium_user'
        await q.edit_message_text("Send user ID:", reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]]))
    else:
        await q.answer("Coming soon.", show_alert=True)


# ══════════════════════════════════════════════════════════════
#  PAGINATION VIEWS
# ══════════════════════════════════════════════════════════════

async def show_user_list(update, context, page):
    q = update.callback_query; limit = 10; offset = page * limit
    users = await get_users_paginated(offset, limit)
    total = await count_users()
    pages = max((total + limit - 1) // limit, 1)
    text  = f"👥 <b>Users (Page {page+1}/{pages})</b>\n\n"
    kb    = []
    for u in users:
        uid, uname, fname, banned, prem, creds = (
            u['user_id'], u['username'], u['first_name'],
            u['is_banned'], u['is_premium'], u['credits']
        )
        name = fname or str(uid)
        stat = "🚫" if banned else ("⭐" if prem else "✅")
        kb.append([InlineKeyboardButton(f"{stat} {name} | 💰{creds}", callback_data=f"userdetail_{uid}")])
        row = [
            InlineKeyboardButton("🚫 Ban" if not banned else "✅ Unban", callback_data=f"toggle_ban_{uid}"),
            InlineKeyboardButton("💳 Credits", callback_data=f"add_credits_{uid}"),
            InlineKeyboardButton("⭐ Premium" if not prem else "❌ Rem.Prem", callback_data=f"{'make_premium_' if not prem else 'remove_premium_'}{uid}"),
        ]
        kb.append(row)
    nav = []
    if page > 0:         nav.append(InlineKeyboardButton("◀️", callback_data=f"userlist_page_{page-1}"))
    if page < pages - 1: nav.append(InlineKeyboardButton("▶️", callback_data=f"userlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_user_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_user_list(update, context, page)

async def user_detail_popup(update, context):
    q   = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[1])
    user = await get_user(uid)
    text = (
        f"👤 {user.get('first_name','N/A')} (@{user.get('username','')})\n"
        f"ID: {uid}\n"
        f"Credits: {user['credits']}\n"
        f"Premium: {'Yes' if user['is_premium'] else 'No'}\n"
        f"Banned: {'Yes' if user['is_banned'] else 'No'}"
    )
    await q.answer(text, show_alert=True)

async def show_premium_list(update, context, page):
    q = update.callback_query; limit = 10; offset = page * limit
    async with database.pool.acquire() as conn:
        rows  = await conn.fetch(
            "SELECT user_id, username, first_name, premium_expiry FROM users "
            "WHERE is_premium=TRUE ORDER BY user_id LIMIT $1 OFFSET $2", limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium=TRUE")
    pages = max((total + limit - 1) // limit, 1)
    text  = f"⭐ <b>Premium Users (Page {page+1}/{pages})</b>\n\n"
    kb    = []
    for u in rows:
        name    = u['first_name'] or str(u['user_id'])
        exp_str = u['premium_expiry'].strftime('%Y-%m-%d') if u['premium_expiry'] else 'Permanent'
        kb.append([InlineKeyboardButton(f"{name} | Exp: {exp_str}", callback_data=f"userdetail_{u['user_id']}")])
        kb.append([InlineKeyboardButton("❌ Remove Premium", callback_data=f"remove_premium_{u['user_id']}")])
    nav = []
    if page > 0:         nav.append(InlineKeyboardButton("◀️", callback_data=f"premiumlist_page_{page-1}"))
    if page < pages - 1: nav.append(InlineKeyboardButton("▶️", callback_data=f"premiumlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_premium_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_premium_list(update, context, page)

async def show_admin_list(update, context, page):
    q = update.callback_query; limit = 10; offset = page * limit
    admins = await get_admins_paginated(offset, limit)
    total  = await count_admins()
    pages  = max((total + limit - 1) // limit, 1)
    text   = f"👑 <b>Admins (Page {page+1}/{pages})</b>\n\n"
    kb     = []
    for a in admins:
        name = a['first_name'] or str(a['user_id'])
        kb.append([InlineKeyboardButton(name, callback_data=f"userdetail_{a['user_id']}")])
        if a['user_id'] != OWNER_ID:
            kb.append([InlineKeyboardButton("❌ Demote", callback_data=f"admintoggle_{a['user_id']}")])
    nav = []
    if page > 0:         nav.append(InlineKeyboardButton("◀️", callback_data=f"adminlist_page_{page-1}"))
    if page < pages - 1: nav.append(InlineKeyboardButton("▶️", callback_data=f"adminlist_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_admin_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_admin_list(update, context, page)

async def show_keys_list(update, context, page):
    q = update.callback_query; limit = 10; offset = page * limit
    async with database.pool.acquire() as conn:
        keys  = await conn.fetch(
            "SELECT key, created_by, expires_at, is_active, total_requests_allowed, requests_made "
            "FROM api_keys ORDER BY created_at DESC LIMIT $1 OFFSET $2", limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM api_keys")
    pages = max((total + limit - 1) // limit, 1)
    text  = f"🔑 <b>All Keys (Page {page+1}/{pages})</b>\n\n"
    kb    = []
    for k in keys:
        status = "✅" if k['is_active'] else "❌"
        total_r, used_r = k['total_requests_allowed'], k['requests_made']
        req_info = f" | Req: {max(0,total_r-used_r)}/{total_r}" if total_r else " | Req: ∞"
        text += f"{status} <code>{k['key'][:20]}...</code> Exp:{k['expires_at'].strftime('%Y-%m-%d')}{req_info}\n"
        kb.append([InlineKeyboardButton(
            "Deactivate" if k['is_active'] else "Activate", callback_data=f"keytoggle_{k['key']}"
        )])
        kb.append([InlineKeyboardButton("🗑 Delete", callback_data=f"delete_key_{k['key']}")])
    nav = []
    if page > 0:         nav.append(InlineKeyboardButton("◀️", callback_data=f"keys_page_{page-1}"))
    if page < pages - 1: nav.append(InlineKeyboardButton("▶️", callback_data=f"keys_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([back_btn("menu_admin")])
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def paginated_keys_list(update, context):
    page = int(update.callback_query.data.split('_')[-1])
    await show_keys_list(update, context, page)


# ══════════════════════════════════════════════════════════════
#  ACTION HANDLERS
# ══════════════════════════════════════════════════════════════

async def toggle_ban(update, context):
    q   = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=NOT is_banned WHERE user_id=$1", uid)
        banned = await conn.fetchval("SELECT is_banned FROM users WHERE user_id=$1", uid)
    await q.answer(f"User {'banned' if banned else 'unbanned'}.", show_alert=True)
    await show_user_list(update, context, 0)

async def add_credits_prompt(update, context):
    q   = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    context.user_data['target_user']  = uid
    context.user_data['admin_state']  = 'awaiting_credit_amount'
    await q.edit_message_text(
        f"Amount of credits to add for user {uid}:",
        reply_markup=InlineKeyboardMarkup([[back_btn("admin_users")]])
    )

async def remove_premium_handler(update, context):
    q   = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    await remove_premium(uid)
    await q.answer("Premium removed.", show_alert=True)
    await show_premium_list(update, context, 0)

async def make_premium_prompt(update, context):
    q   = update.callback_query
    await q.answer()
    uid = int(q.data.split('_')[-1])
    context.user_data['target_premium_user'] = uid
    context.user_data['admin_state']         = 'awaiting_premium_days'
    await q.edit_message_text(
        f"Days of premium for user {uid} (or type 'permanent'):",
        reply_markup=InlineKeyboardMarkup([[back_btn("admin_premium")]])
    )

async def toggle_admin(update, context):
    q   = update.callback_query
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
    q   = update.callback_query
    await q.answer()
    key = q.data.split('_', 1)[1]
    async with database.pool.acquire() as conn:
        active = await conn.fetchval("SELECT is_active FROM api_keys WHERE key=$1", key)
    if active:
        await deactivate_api_key(key)
        await q.answer("Key deactivated.", show_alert=True)
    else:
        await activate_api_key(key)
        await q.answer("Key activated.", show_alert=True)
    await show_keys_list(update, context, 0)

async def confirm_delete_key(update, context):
    q   = update.callback_query
    await q.answer()
    key = q.data.split("delete_key_", 1)[1]
    context.user_data['del_key'] = key
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_delete_key_{key}")],
        [InlineKeyboardButton("❌ Cancel",       callback_data="close_panel")],
    ])
    await q.edit_message_text(
        f"Delete key <code>{key[:20]}...</code>?", parse_mode='HTML', reply_markup=kb
    )

async def execute_delete_key(update, context):
    q   = update.callback_query
    await q.answer()
    key = q.data.split("confirm_delete_key_", 1)[1]
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM api_keys WHERE key=$1", key)
    await q.edit_message_text(
        f"✅ Key deleted: <code>{key[:20]}...</code>", parse_mode='HTML'
    )

async def broadcast_type(update, context):
    q     = update.callback_query
    btype = q.data.split('_')[1]
    context.user_data['broadcast_type'] = btype
    await q.edit_message_text(
        f"Send the {btype} to broadcast to all users:",
        reply_markup=InlineKeyboardMarkup([[back_btn("menu_admin")]])
    )


# ══════════════════════════════════════════════════════════════
#  TEXT MESSAGE HANDLER
# ══════════════════════════════════════════════════════════════

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # ── Redeem (any user) ────────────────────────────────────
    if context.user_data.get('awaiting_redeem'):
        context.user_data.pop('awaiting_redeem')
        if await redeem_code(uid, text):
            await update.message.reply_text("✅ Code redeemed!")
        else:
            await update.message.reply_text("❌ Invalid, expired or already used code.")
        return

    # ── Admin only below ─────────────────────────────────────
    if not await is_admin(uid):
        return

    state = context.user_data.get('admin_state')
    if not state:
        return

    # ─── Credit flow ──────────────────────────────────────────
    if state == 'awaiting_user_for_credits':
        try:
            target = int(text)
            context.user_data['target_user']  = target
            context.user_data['admin_state']  = 'awaiting_credit_amount'
            await update.message.reply_text("Amount of credits to add:")
        except:
            await update.message.reply_text("Invalid user ID.")
            context.user_data.pop('admin_state', None)

    elif state == 'awaiting_credit_amount':
        try:
            amt    = int(text)
            target = context.user_data.pop('target_user')
            await add_credits(target, amt)
            await update.message.reply_text(f"✅ Added {amt} credits to {target}.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid amount.")

    # ─── Redeem code creation ─────────────────────────────────
    elif state == 'awaiting_redeem_credits':
        try:
            creds = int(text)
            context.user_data['redeem_creds'] = creds
            context.user_data['admin_state']  = 'awaiting_redeem_maxuses'
            await update.message.reply_text("Max uses for this code:")
        except:
            await update.message.reply_text("Invalid number.")

    elif state == 'awaiting_redeem_maxuses':
        try:
            maxu  = int(text)
            creds = context.user_data.pop('redeem_creds')
            code  = secrets.token_hex(4).upper()
            await create_redeem_code(code, creds, uid, maxu)
            await update.message.reply_text(
                f"✅ Redeem Code Created!\n\n"
                f"Code: <code>{code}</code>\n"
                f"Credits: {creds}\nMax Uses: {maxu}",
                parse_mode='HTML'
            )
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")

    # ─── DM ───────────────────────────────────────────────────
    elif state == 'awaiting_dm_user':
        try:
            target = int(text)
            context.user_data['dm_target'] = target
            context.user_data['admin_state'] = 'awaiting_dm_message'
            await update.message.reply_text("Message to send:")
        except:
            await update.message.reply_text("Invalid user ID.")

    elif state == 'awaiting_dm_message':
        target = context.user_data.pop('dm_target')
        try:
            await application.bot.send_message(target, text, parse_mode='HTML')
            await update.message.reply_text("✅ Sent.")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
        context.user_data.pop('admin_state', None)

    # ─── Bulk DM ──────────────────────────────────────────────
    elif state == 'awaiting_bulkdm_ids':
        ids = [int(x.strip()) for x in text.replace('\n', ',').split(',') if x.strip().isdigit()]
        context.user_data['bulk_ids']    = ids
        context.user_data['admin_state'] = 'awaiting_bulkdm_message'
        await update.message.reply_text(f"Got {len(ids)} IDs. Send your message:")

    elif state == 'awaiting_bulkdm_message':
        ids     = context.user_data.pop('bulk_ids')
        success = 0
        for i in ids:
            try:
                await application.bot.send_message(i, text, parse_mode='HTML')
                success += 1
            except:
                pass
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ Sent to {success}/{len(ids)} users.")
        context.user_data.pop('admin_state', None)

    # ─── Custom key flow ──────────────────────────────────────
    elif state == 'awaiting_custom_key_string':
        key = text.strip()
        if not key:
            await update.message.reply_text("Key cannot be empty. Try again:")
            return
        if await key_exists(key):  # BUG FIX: uses pool.acquire()
            await update.message.reply_text("Key already exists. Choose another:")
            return
        context.user_data['cust_key']    = key
        context.user_data['admin_state'] = 'awaiting_custom_key_expiry'
        await update.message.reply_text("Expiry in days (e.g. 30) or type 'permanent':")

    elif state == 'awaiting_custom_key_expiry':
        if text.lower() == 'permanent':
            context.user_data['cust_expiry'] = 'permanent'
        else:
            try:
                days = int(text)
                if days <= 0: raise ValueError
                context.user_data['cust_expiry'] = days
            except:
                await update.message.reply_text("Invalid. Enter days (e.g. 30) or 'permanent':")
                return
        context.user_data['admin_state'] = 'awaiting_custom_key_totalreq'
        await update.message.reply_text("Total requests allowed (0 = unlimited):")

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
            context.user_data['cust_key'], uid,
            expires_days=expiry_days,
            rate_limit=context.user_data['cust_rate'],
            total_requests=context.user_data['cust_total'],
            custom_name=f"{context.user_data['custkey_api'].upper()}_Custom"
        )
        await log_key_gen(uid, context.user_data['cust_key'], context.user_data['custkey_api'])

        api_type   = context.user_data['custkey_api']
        cfg        = API_ENDPOINTS[api_type]
        endpoint   = (f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}"
                      f"?key={context.user_data['cust_key']}&{cfg['param_name']}={cfg['param_example']}")
        await update.message.reply_text(
            f"✅ <b>Custom Key Created!</b>\n\n"
            f"🔑 Key: <code>{context.user_data['cust_key']}</code>\n"
            f"📅 Expiry: {context.user_data['cust_expiry']} days\n"
            f"📊 Requests: {context.user_data['cust_total'] or 'Unlimited'}\n"
            f"⚡ Rate: {context.user_data['cust_rate']}/min\n\n"
            f"🔗 Example:\n<code>{endpoint}</code>",
            parse_mode='HTML'
        )
        context.user_data.pop('admin_state', None)

    # ─── Pricing flow ─────────────────────────────────────────
    elif state == 'awaiting_pricing_plan':
        if text.lower() in ['weekly', 'monthly']:
            context.user_data['pricing_plan']  = text.lower()
            context.user_data['admin_state']   = 'awaiting_pricing_credits'
            await update.message.reply_text("New price in credits:")
        else:
            await update.message.reply_text("Invalid. Type 'weekly' or 'monthly':")

    elif state == 'awaiting_pricing_credits':
        try:
            price = int(text)
            api   = context.user_data.pop('pricing_api')
            plan  = context.user_data.pop('pricing_plan')
            async with database.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE api_plans SET price_credits=$1 WHERE api_type=$2 AND plan_name=$3",
                    price, api, plan
                )
            await update.message.reply_text(f"✅ Updated {api.upper()} {plan} = {price} credits.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")

    # ─── Premium flow ─────────────────────────────────────────
    elif state == 'awaiting_premium_user':
        try:
            target = int(text)
            context.user_data['target_premium_user'] = target
            context.user_data['admin_state']         = 'awaiting_premium_days'
            await update.message.reply_text("Days (or 'permanent'):")
        except:
            await update.message.reply_text("Invalid user ID.")

    elif state == 'awaiting_premium_days':
        days_txt = text.lower()
        target   = context.user_data.pop('target_premium_user')
        if days_txt == 'permanent':
            await set_premium(target, days=None)
        else:
            try:
                await set_premium(target, days=int(days_txt))
            except:
                await update.message.reply_text("Invalid. Enter days or 'permanent'.")
                return
        await update.message.reply_text(f"✅ Premium set for {target}.")
        context.user_data.pop('admin_state', None)


# ══════════════════════════════════════════════════════════════
#  MEDIA BROADCAST
# ══════════════════════════════════════════════════════════════

async def handle_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    btype = context.user_data.get('broadcast_type')
    if not btype:
        return
    msg = update.message
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned=FALSE")
    users   = [r['user_id'] for r in rows]
    success = 0
    for uid in users:
        try:
            if btype == 'text':
                await application.bot.send_message(uid, msg.text, parse_mode='HTML')
            elif btype == 'photo':
                await application.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif btype == 'video':
                await application.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif btype == 'doc':
                await application.bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    context.user_data.pop('broadcast_type', None)
    await update.message.reply_text(f"✅ Broadcast sent to {success}/{len(users)} users.")


# ══════════════════════════════════════════════════════════════
#  BACKGROUND TASKS
# ══════════════════════════════════════════════════════════════

async def self_ping():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(SELF_PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(f"{RENDER_EXTERNAL_URL}/health", timeout=aiohttp.ClientTimeout(total=10))
            await application.bot.get_me()
        except:
            pass

async def premium_expiry_check():
    while True:
        await asyncio.sleep(3600)
        async with database.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_premium=FALSE "
                "WHERE is_premium=TRUE AND premium_expiry IS NOT NULL AND premium_expiry < NOW()"
            )

async def subscription_expiry_check():
    """Mark expired subscriptions inactive."""
    while True:
        await asyncio.sleep(1800)
        async with database.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_subscriptions SET is_active=FALSE "
                "WHERE is_active=TRUE AND end_date < NOW()"
            )

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


# ══════════════════════════════════════════════════════════════
#  STARTUP / SHUTDOWN
# ══════════════════════════════════════════════════════════════

async def on_startup():
    global http_session
    await init_db()
    database.pool = database.pool   # pool already set in init_db
    init_sheets()
    http_session = aiohttp.ClientSession()
    await application.initialize()
    await application.bot.set_my_commands([
        BotCommand("start",    "Start the bot"),
        BotCommand("balance",  "Check credits"),
        BotCommand("buy",      "Purchase subscription"),
        BotCommand("redeem",   "Redeem a code"),
        BotCommand("referral", "Get referral link"),
        BotCommand("admin",    "Admin panel"),
    ])
    if BOT_MODE == "webhook":
        await application.bot.set_webhook(
            url=f"{RENDER_EXTERNAL_URL}/webhook", secret_token=WEBHOOK_SECRET
        )
        logger.info(f"✅ Webhook set → {RENDER_EXTERNAL_URL}/webhook")
    else:
        asyncio.create_task(application.run_polling())
        logger.info("✅ Polling started")

    asyncio.create_task(self_ping())
    asyncio.create_task(premium_expiry_check())
    asyncio.create_task(subscription_expiry_check())
    asyncio.create_task(daily_backup())
    logger.info("🚀 Bot is live!")

async def on_shutdown():
    if http_session:
        await http_session.close()
    await application.stop()
    await application.shutdown()
    await close_db()


# ══════════════════════════════════════════════════════════════
#  HANDLER REGISTRATION
# ══════════════════════════════════════════════════════════════

application.add_handler(CommandHandler("start",    start))
application.add_handler(CommandHandler("balance",  balance_command))
application.add_handler(CommandHandler("buy",      buy_command))
application.add_handler(CommandHandler("redeem",   redeem_command))
application.add_handler(CommandHandler("referral", referral_command))
application.add_handler(CommandHandler("admin",    admin_command))

# Single unified callback router — no duplicate patterns
application.add_handler(CallbackQueryHandler(check_join_cb,  pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(menu_router,    pattern="^(menu_|cat_|gen_|plan_|custkey_|userlist_page_|premiumlist_page_|adminlist_page_|keys_page_|toggle_ban_|add_credits_|remove_premium_|make_premium_|userdetail_|admintoggle_|keytoggle_|delete_key_|confirm_delete_key_|bcast_|admin_|close_panel)"))

# Text / media
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,                      handle_text))
application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_broadcast_media))


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import hypercorn.asyncio
    from hypercorn.config import Config as HyperConfig
    hcfg       = HyperConfig()
    hcfg.bind  = [f"0.0.0.0:{PORT}"]
    loop       = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(on_startup())
    loop.run_until_complete(hypercorn.asyncio.serve(app, hcfg))
