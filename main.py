# main.py - QUART + PTB 21.x ASYNC - ALL FEATURES + WEBHOOK ROUTE FIXED

import json
import asyncio
import secrets
import time
import re
import aiohttp
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

# Quart (async Flask replacement)
from quart import Quart, request, jsonify

# Telegram Bot
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, InputMediaPhoto, InputMediaVideo, InputMediaDocument,
    InputMediaAudio, InputMediaAnimation, InputMedia
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

# Local modules
from config import *
from database import *

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# ============================================
# QUART APP (For Proxy API + Telegram Webhook)
# ============================================
app = Quart(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['PROVIDE_AUTOMATIC_OPTIONS'] = True

# In-memory cache (fallback if no Redis)
cache: Dict[str, Tuple[float, any]] = {}

# Global aiohttp session for external API calls
http_session: Optional[aiohttp.ClientSession] = None

# ============================================
# PTB APPLICATION
# ============================================
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ============================================
# HELPER FUNCTIONS (Branding Removal, etc.)
# ============================================
def remove_branding(data, extra_blacklist=None):
    if extra_blacklist is None:
        extra_blacklist = []
    blacklist = set([term.lower() for term in GLOBAL_BLACKLIST] +
                    [term.lower() for term in extra_blacklist])

    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return [remove_branding(item, extra_blacklist) for item in data
                if remove_branding(item, extra_blacklist) not in ("", None)]
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if k.lower() in blacklist:
                continue
            cleaned_val = remove_branding(v, extra_blacklist)
            if cleaned_val not in ("", None):
                cleaned[k] = cleaned_val
        return cleaned
    return data

async def get_cached(key: str):
    if key in cache:
        ts, data = cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        else:
            del cache[key]
    return None

async def set_cached(key: str, data: str):
    cache[key] = (time.time(), data)

# ============================================
# QUART ROUTES (Proxy API)
# ============================================
@app.route('/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/api/v1/<api_type>')
async def proxy_api(api_type):
    if api_type not in API_ENDPOINTS:
        return jsonify({"error": "Invalid API type. Use 'num' or 'tg'."}), 400

    api_config = API_ENDPOINTS[api_type]
    if not api_config.get('enabled', True):
        return jsonify({"error": "This API is currently disabled."}), 403

    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    valid, user_id, rate_limit = await validate_api_key(key)
    if not valid:
        return jsonify({"error": "Invalid or expired API key"}), 403

    if not await is_admin(user_id):
        if not await has_active_subscription(user_id, api_type):
            return jsonify({"error": f"No active subscription for {api_type.upper()} API."}), 403

    # Rate limiting
    rate_key = f"rate_{key}"
    now = time.time()
    if rate_key in cache:
        count, window_start = cache[rate_key]
        if now - window_start > 60:
            count = 1
            cache[rate_key] = (count, now)
        else:
            if count >= rate_limit:
                return jsonify({"error": "Rate limit exceeded."}), 429
            cache[rate_key] = (count + 1, window_start)
    else:
        cache[rate_key] = (1, now)

    param_name = api_config['param_name']
    param_value = request.args.get(param_name)
    if not param_value:
        return jsonify({"error": f"Missing '{param_name}' parameter"}), 400

    if 'param_validation' in api_config:
        if not re.match(api_config['param_validation'], param_value):
            return jsonify({"error": f"Invalid {param_name} format"}), 400

    cache_key = f"api_{api_type}_{param_value}"
    cached = await get_cached(cache_key)
    if cached:
        return app.response_class(response=cached, status=200, mimetype='application/json')

    external_api_key = api_config['external_api_key']
    url = api_config['url_template'].format(api_key=external_api_key, param=param_value)

    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return jsonify({"error": f"Upstream API returned {resp.status}"}), 502
            data = await resp.json()
    except asyncio.TimeoutError:
        return jsonify({"error": "Upstream API timeout"}), 504
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 502

    extra_blacklist = api_config.get('extra_blacklist', [])
    cleaned = remove_branding(data, extra_blacklist)
    cleaned['branding'] = BRANDING

    pretty_json = json.dumps(cleaned, indent=2, ensure_ascii=False)
    await set_cached(cache_key, pretty_json)

    return app.response_class(response=pretty_json, status=200, mimetype='application/json')

# ============================================
# TELEGRAM WEBHOOK ROUTE (THIS WAS MISSING!)
# ============================================
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    """Handle incoming Telegram updates via webhook."""
    # Verify secret token for security
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        logger.warning("Unauthorized webhook attempt")
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = await request.get_json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# TELEGRAM BOT - KEYBOARD BUILDERS
# ============================================
def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="menu_genkey"),
        InlineKeyboardButton("📘 API Docs", callback_data="menu_apihelp")],
        [InlineKeyboardButton("👤 My Keys", callback_data="menu_mykeys"),
        InlineKeyboardButton("💰 Balance & Plans", callback_data="menu_balance")],
        [InlineKeyboardButton("🔗 Referral", callback_data="menu_referral"),
        InlineKeyboardButton("🎟️ Redeem Code", callback_data="menu_redeem")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("🛡️ Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(buttons)

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users"),
        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔑 All API Keys", callback_data="admin_keys"),
        InlineKeyboardButton("💳 Add Credits", callback_data="admin_addcredits")],
        [InlineKeyboardButton("⭐ Premium Users", callback_data="admin_premium"),
        InlineKeyboardButton("🎟️ Gen Redeem Code", callback_data="admin_genredeem")],
        [InlineKeyboardButton("👑 Manage Admins", callback_data="admin_admins"),
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Set Pricing", callback_data="admin_pricing"),
        InlineKeyboardButton("📨 DM User", callback_data="admin_dm")],
        [InlineKeyboardButton("📨 Bulk DM", callback_data="admin_bulkdm")],
        [InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ])

def back_button(callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton("🔙 Back", callback_data=callback_data)

# ============================================
# FORCE JOIN CHECK
# ============================================
async def check_force_join(user_id: int) -> Tuple[bool, List[Dict]]:
    if await is_admin(user_id):
        return True, []
    if PREMIUM_EXEMPT_FORCE_JOIN and await is_premium(user_id):
        return True, []

    missing = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            if member.status in ['left', 'kicked']:
                missing.append(channel)
        except Exception:
            missing.append(channel)
    return len(missing) == 0, missing

async def send_force_join_message(chat_id: int, missing: List[Dict]):
    text = "⚠️ <b>Please join these channels to use the bot:</b>\n\n"
    keyboard = []
    for ch in missing:
        keyboard.append([InlineKeyboardButton(f"Join {ch['name']}", url=ch['link'])])
    keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    await application.bot.send_message(chat_id, text, parse_mode='HTML',
                                       reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================
# LOGGING TO CHANNEL
# ============================================
async def log_key_generation(user_id: int, api_key: str, api_type: str = "unknown"):
    user = await get_user(user_id)
    text = (
        f"🔑 <b>New API Key Generated</b>\n\n"
        f"👤 <b>User:</b> {user.get('first_name', 'N/A')} "
        f"(@{user.get('username', 'no_username')}) [<code>{user_id}</code>]\n"
        f"🔹 <b>API Type:</b> {api_type.upper()}\n"
        f"🗝️ <b>Key:</b> <code>{api_key}</code>\n"
        f"📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        await application.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to log to channel: {e}")

# ============================================
# COMMAND: /start
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    db_user = await get_user(user_id)
    await update_user_info(user_id, user.username, user.first_name, user.last_name)

    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0][4:])
            if referrer_id != user_id:
                if await set_referrer(user_id, referrer_id):
                    context.user_data['pending_referrer'] = referrer_id
        except:
            pass

    joined, missing = await check_force_join(user_id)
    if not joined:
        await send_force_join_message(user_id, missing)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET joined_force_channels=1 WHERE user_id=?", (user_id,))
        await db.commit()
    if 'pending_referrer' in context.user_data:
        referrer_id = context.user_data.pop('pending_referrer')
        await add_credits(referrer_id, REFERRAL_REWARD_CREDITS)
        try:
            await application.bot.send_message(
                referrer_id,
                f"🎉 <b>Referral Bonus!</b>\nYou earned {REFERRAL_REWARD_CREDITS} credits."
            )
        except:
            pass

    is_admin_flag = await is_admin(user_id)
    text = f"✨ <b>Welcome, {user.first_name}!</b> ✨\n\nUse the menu below:"
    await update.message.reply_text(text, parse_mode='HTML',
                                    reply_markup=main_menu_keyboard(is_admin_flag))

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    joined, missing = await check_force_join(user_id)
    if joined:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE users SET joined_force_channels=1 WHERE user_id=?", (user_id,))
            await db.commit()
        await query.edit_message_text("✅ Thank you! Press /start to see the menu.")
    else:
        await query.answer("You haven't joined all channels yet.", show_alert=True)

# ============================================
# MENU HANDLERS
# ============================================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    is_admin_flag = await is_admin(user_id)

    if not is_admin_flag and data not in ["check_join", "close_panel"]:
        joined, missing = await check_force_join(user_id)
        if not joined:
            await query.edit_message_text("⚠️ Please join all channels first.",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("🔄 Try Again", callback_data="check_join")
                                          ]]))
            return

    if data == "menu_genkey":
        await genkey_menu(update, context)
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
    elif data == "menu_admin":
        if is_admin_flag:
            await query.edit_message_text("🛡️ <b>Admin Control Center</b>", parse_mode='HTML',
                                          reply_markup=admin_panel_keyboard())
        else:
            await query.answer("Access denied.", show_alert=True)
    elif data == "close_panel":
        await query.delete_message()
    elif data.startswith("admin_"):
        await admin_menu_handler(update, context)
    elif data.startswith("gen_"):
        await gen_specific_key(update, context)
    elif data.startswith("plan_"):
        await buy_plan_handler(update, context)
    elif data.startswith("userlist_page_"):
        await paginated_user_list(update, context)
    elif data.startswith("premiumlist_page_"):
        await paginated_premium_list(update, context)
    elif data.startswith("adminlist_page_"):
        await paginated_admin_list(update, context)
    elif data.startswith("keys_page_"):
        await paginated_keys_list(update, context)
    elif data.startswith("toggle_ban_"):
        await toggle_ban_handler(update, context)
    elif data.startswith("add_credits_"):
        await add_credits_prompt(update, context)
    elif data.startswith("remove_premium_"):
        await remove_premium_handler(update, context)
    elif data.startswith("make_premium_"):
        await make_premium_prompt(update, context)
    elif data.startswith("bcast_"):
        await broadcast_type_selected(update, context)
    elif data == "check_join":
        await check_join_callback(update, context)
    else:
        await query.answer("Not implemented.", show_alert=True)

async def genkey_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    is_admin_flag = await is_admin(user_id)
    if not is_admin_flag:
        has_num = await has_active_subscription(user_id, 'num')
        has_tg = await has_active_subscription(user_id, 'tg')
        if not has_num and not has_tg:
            await query.edit_message_text(
                "❌ No active subscription.\nUse /buy to purchase a plan.",
                reply_markup=InlineKeyboardMarkup([[back_button("menu_balance")]])
            )
            return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Number Info API", callback_data="gen_num")],
        [InlineKeyboardButton("📱 Telegram to Number", callback_data="gen_tg")],
        [back_button("menu_start")]
    ])
    await query.edit_message_text("Select API type for your new key:", reply_markup=keyboard)

async def gen_specific_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    api_type = query.data.split('_')[1]
    user_id = update.effective_user.id
    if not await is_admin(user_id) and not await has_active_subscription(user_id, api_type):
        await query.edit_message_text(f"❌ No active subscription for {api_type.upper()} API.",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_balance")]]))
        return
    new_key = await generate_random_key()
    await create_api_key(new_key, user_id, expires_days=30, rate_limit=80, custom_name=f"{api_type.upper()}_Key")
    await log_key_generation(user_id, new_key, api_type)
    example = API_ENDPOINTS[api_type]['param_example']
    endpoint = f"{RENDER_EXTERNAL_URL}/api/v1/{api_type}?key={new_key}&{API_ENDPOINTS[api_type]['param_name']}={example}"
    text = f"✅ <b>API Key Generated!</b>\n\n<code>{new_key}</code>\n\n🔹 <b>Usage Example:</b>\n<code>{endpoint}</code>"
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_genkey")]]))

async def apihelp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "📘 <b>API Documentation</b>\n\n"
    for key, cfg in API_ENDPOINTS.items():
        text += f"<b>{cfg['name']}</b>\n<code>{RENDER_EXTERNAL_URL}/api/v1/{key}?key=YOUR_KEY&{cfg['param_name']}={cfg['param_example']}</code>\n\n"
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_start")]]))

async def mykeys_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    keys = await list_api_keys(created_by=user_id)
    if not keys:
        text = "You have no API keys."
    else:
        text = "<b>Your API Keys:</b>\n\n"
        for k in keys[:5]:
            text += f"<code>{k[0]}</code> | Exp: {k[1][:10]} | {'✅' if k[4] else '❌'}\n"
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_start")]]))

async def balance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    credits = await get_user_credits(user_id)
    has_num = await has_active_subscription(user_id, 'num')
    has_tg = await has_active_subscription(user_id, 'tg')
    text = f"💰 <b>Your Balance</b>\nCredits: <b>{credits}</b>\n\n📞 Number API: {'✅' if has_num else '❌'}\n📱 TG API: {'✅' if has_tg else '❌'}\n\nSelect a plan:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Number Weekly (15)", callback_data="plan_num_weekly")],
        [InlineKeyboardButton("📞 Number Monthly (30)", callback_data="plan_num_monthly")],
        [InlineKeyboardButton("📱 TG Weekly (15)", callback_data="plan_tg_weekly")],
        [InlineKeyboardButton("📱 TG Monthly (30)", callback_data="plan_tg_monthly")],
        [back_button("menu_start")]
    ])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)

async def buy_plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    api_type = parts[1]
    plan_name = parts[2]
    user_id = update.effective_user.id
    is_admin_flag = await is_admin(user_id)
    plan = await get_plan(api_type, plan_name)
    if not plan:
        await query.answer("Plan not found.", show_alert=True)
        return
    plan_id, price, days = plan
    if is_admin_flag:
        async with aiosqlite.connect(DB_FILE) as db:
            start = datetime.now().isoformat()
            end = (datetime.now() + timedelta(days=days)).isoformat()
            await db.execute(
                "INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) VALUES (?,?,?,?,?,?)",
                (user_id, api_type, plan_id, start, end, 1))
            await db.commit()
        await query.edit_message_text(f"✅ Admin subscription activated for {api_type.upper()} ({plan_name}).",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_balance")]]))
        return
    credits = await get_user_credits(user_id)
    if credits < price:
        await query.answer(f"Insufficient credits. Need {price}.", show_alert=True)
        return
    success = await create_subscription(user_id, api_type, plan_name)
    if success:
        await query.edit_message_text(f"✅ Subscription purchased!\n{api_type.upper()} - {plan_name} plan activated.",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_balance")]]))
    else:
        await query.answer("Purchase failed.", show_alert=True)

async def referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    bot_username = (await application.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    text = f"🔗 <b>Your Referral Link</b>\n\n<code>{link}</code>\n\nShare and earn {REFERRAL_REWARD_CREDITS} credits per successful referral."
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_start")]]))

async def redeem_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['awaiting_redeem'] = True
    await query.edit_message_text("🎟️ Send the redeem code:",
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_start")]]))

# ============================================
# ADMIN PANEL HANDLERS
# ============================================
async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    if data == "admin_users":
        await show_user_list(update, context, page=0)
    elif data == "admin_keys":
        await show_keys_list(update, context, page=0)
    elif data == "admin_addcredits":
        context.user_data['admin_state'] = 'awaiting_user_for_credits'
        await query.edit_message_text("Send user ID to add credits:",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))
    elif data == "admin_premium":
        await show_premium_list(update, context, page=0)
    elif data == "admin_genredeem":
        context.user_data['admin_state'] = 'awaiting_redeem_credits'
        await query.edit_message_text("Send amount of credits for redeem code:",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))
    elif data == "admin_admins":
        await show_admin_list(update, context, page=0)
    elif data == "admin_stats":
        total = await count_users()
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT COUNT(*) FROM api_keys")
            keys = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_premium=1")
            premium = (await cur.fetchone())[0]
        text = f"📊 <b>Stats</b>\nUsers: {total}\nAPI Keys: {keys}\nPremium: {premium}\nCache: {len(cache)}"
        await query.edit_message_text(text, parse_mode='HTML',
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))
    elif data == "admin_dm":
        context.user_data['admin_state'] = 'awaiting_dm_user'
        await query.edit_message_text("Send user ID to DM:",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))
    elif data == "admin_bulkdm":
        context.user_data['admin_state'] = 'awaiting_bulkdm_ids'
        await query.edit_message_text("Send comma-separated user IDs or upload a text file with one ID per line:",
                                      reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))
    elif data == "admin_broadcast":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Text", callback_data="bcast_text")],
            [InlineKeyboardButton("Photo", callback_data="bcast_photo")],
            [InlineKeyboardButton("Video", callback_data="bcast_video")],
            [InlineKeyboardButton("Document", callback_data="bcast_doc")],
            [back_button("menu_admin")]
        ])
        await query.edit_message_text("Select broadcast type:", reply_markup=keyboard)
    elif data == "admin_pricing":
        context.user_data['admin_state'] = 'awaiting_pricing_api'
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Number API", callback_data="price_num")],
            [InlineKeyboardButton("TG API", callback_data="price_tg")],
            [back_button("menu_admin")]
        ])
        await query.edit_message_text("Select API to set price:", reply_markup=keyboard)
    else:
        await query.answer("Coming soon.", show_alert=True)

async def broadcast_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    media = query.data.replace("bcast_", "")
    context.user_data['broadcast_type'] = media
    await query.edit_message_text(f"Send the {media} to broadcast:",
                                  reply_markup=InlineKeyboardMarkup([[back_button("menu_admin")]]))

# ============================================
# PAGINATION FUNCTIONS
# ============================================
async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit
    users = await get_users_paginated(offset, limit)
    total = await count_users()
    pages = (total + limit - 1) // limit if total > 0 else 1
    text = f"👥 <b>User List (Page {page+1}/{pages})</b>\n\n"
    keyboard = []
    for u in users:
        uid, username, first_name, banned, premium, credits = u
        name = first_name or str(uid)
        status = "🚫" if banned else ("⭐" if premium else "✅")
        btn = InlineKeyboardButton(f"{status} {name} | 💰{credits}", callback_data=f"userdetail_{uid}")
        keyboard.append([btn])
        action_row = []
        if not banned:
            action_row.append(InlineKeyboardButton("🚫 Ban", callback_data=f"toggle_ban_{uid}"))
        else:
            action_row.append(InlineKeyboardButton("✅ Unban", callback_data=f"toggle_ban_{uid}"))
        action_row.append(InlineKeyboardButton("💳 Add Credits", callback_data=f"add_credits_{uid}"))
        if premium:
            action_row.append(InlineKeyboardButton("⭐ Remove Premium", callback_data=f"remove_premium_{uid}"))
        else:
            action_row.append(InlineKeyboardButton("⭐ Make Premium", callback_data=f"make_premium_{uid}"))
        keyboard.append(action_row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"userlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"userlist_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([back_button("menu_admin")])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def paginated_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(update.callback_query.data.split('_')[-1])
    await show_user_list(update, context, page)

async def show_premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT user_id, username, first_name, premium_expiry FROM users WHERE is_premium=1 ORDER BY user_id LIMIT ? OFFSET ?", (limit, offset))
        users = await cur.fetchall()
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_premium=1")
        total = (await cur.fetchone())[0]
    pages = (total + limit - 1) // limit if total > 0 else 1
    text = f"⭐ <b>Premium Users (Page {page+1}/{pages})</b>\n\n"
    keyboard = []
    for u in users:
        uid, username, first_name, expiry = u
        name = first_name or str(uid)
        btn = InlineKeyboardButton(f"{name} | Exp: {expiry[:10] if expiry else 'Permanent'}", callback_data=f"premdetail_{uid}")
        keyboard.append([btn])
        action_row = [InlineKeyboardButton("❌ Remove Premium", callback_data=f"remove_premium_{uid}")]
        keyboard.append(action_row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"premiumlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"premiumlist_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("➕ Add Premium", callback_data="admin_addpremium"), back_button("menu_admin")])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def paginated_premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(update.callback_query.data.split('_')[-1])
    await show_premium_list(update, context, page)

async def show_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit
    admins = await get_admins_paginated(offset, limit)
    total = await count_admins()
    pages = (total + limit - 1) // limit if total > 0 else 1
    text = f"👑 <b>Admin List (Page {page+1}/{pages})</b>\n\n"
    keyboard = []
    for a in admins:
        uid, username, first_name = a
        name = first_name or str(uid)
        btn = InlineKeyboardButton(f"{name}", callback_data=f"admindetail_{uid}")
        keyboard.append([btn])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"adminlist_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"adminlist_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([back_button("menu_admin")])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def paginated_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(update.callback_query.data.split('_')[-1])
    await show_admin_list(update, context, page)

async def show_keys_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT key, created_by, expires_at, is_active FROM api_keys LIMIT ? OFFSET ?", (limit, offset))
        keys = await cur.fetchall()
        cur = await db.execute("SELECT COUNT(*) FROM api_keys")
        total = (await cur.fetchone())[0]
    pages = (total + limit - 1) // limit if total > 0 else 1
    text = f"🔑 <b>API Keys (Page {page+1}/{pages})</b>\n\n"
    keyboard = []
    for k in keys:
        key, created_by, expires, active = k
        status = "✅" if active else "❌"
        text += f"{status} <code>{key[:20]}...</code> | Exp: {expires[:10]}\n"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"keys_page_{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"keys_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([back_button("menu_admin")])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def paginated_keys_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(update.callback_query.data.split('_')[-1])
    await show_keys_list(update, context, page)

# ============================================
# SPECIFIC ACTION HANDLERS
# ============================================
async def toggle_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split('_')[-1])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_banned = NOT is_banned WHERE user_id=?", (uid,))
        await db.commit()
        cur = await db.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,))
        banned = (await cur.fetchone())[0]
    await query.answer(f"User {'banned' if banned else 'unbanned'} successfully.", show_alert=True)
    await show_user_list(update, context, page=0)

async def add_credits_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split('_')[-1])
    context.user_data['target_user'] = uid
    context.user_data['admin_state'] = 'awaiting_credit_amount'
    await query.edit_message_text(f"Send amount of credits to add for user {uid}:",
                                  reply_markup=InlineKeyboardMarkup([[back_button("admin_users")]]))

async def remove_premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split('_')[-1])
    await remove_premium(uid)
    await query.answer("Premium removed.", show_alert=True)
    await show_premium_list(update, context, page=0)

async def make_premium_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split('_')[-1])
    context.user_data['target_premium_user'] = uid
    context.user_data['admin_state'] = 'awaiting_premium_days'
    await query.edit_message_text(f"Send number of days for premium (or 'permanent'):",
                                  reply_markup=InlineKeyboardMarkup([[back_button("admin_premium")]]))

# ============================================
# MESSAGE HANDLERS FOR ADMIN STATES & REDEEM
# ============================================
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get('awaiting_redeem'):
        context.user_data.pop('awaiting_redeem')
        success = await redeem_code(user_id, text)
        if success:
            await update.message.reply_text("✅ Code redeemed successfully! Credits added.")
        else:
            await update.message.reply_text("❌ Invalid or expired code.")
        return

    if not await is_admin(user_id):
        return

    state = context.user_data.get('admin_state')
    if not state:
        return

    if state == 'awaiting_user_for_credits':
        try:
            uid = int(text)
            context.user_data['target_user'] = uid
            context.user_data['admin_state'] = 'awaiting_credit_amount'
            await update.message.reply_text("Send amount of credits to add:")
        except:
            await update.message.reply_text("Invalid user ID.")
            context.user_data.pop('admin_state', None)
    elif state == 'awaiting_credit_amount':
        try:
            amount = int(text)
            uid = context.user_data.pop('target_user')
            await add_credits(uid, amount)
            await update.message.reply_text(f"✅ Added {amount} credits to user {uid}.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid amount.")
    elif state == 'awaiting_redeem_credits':
        try:
            credits = int(text)
            context.user_data['redeem_credits'] = credits
            context.user_data['admin_state'] = 'awaiting_redeem_maxuses'
            await update.message.reply_text("Send max uses (or '1'):")
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_redeem_maxuses':
        try:
            max_uses = int(text)
            credits = context.user_data['redeem_credits']
            code = secrets.token_hex(4).upper()
            await create_redeem_code(code, credits, user_id, max_uses)
            await update.message.reply_text(f"✅ Redeem code generated: <code>{code}</code>\nCredits: {credits}\nUses: {max_uses}")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_dm_user':
        try:
            uid = int(text)
            context.user_data['dm_target'] = uid
            context.user_data['admin_state'] = 'awaiting_dm_message'
            await update.message.reply_text("Send the message to DM:")
        except:
            await update.message.reply_text("Invalid user ID.")
    elif state == 'awaiting_dm_message':
        uid = context.user_data.pop('dm_target')
        try:
            await application.bot.send_message(uid, text, parse_mode='HTML')
            await update.message.reply_text(f"✅ Message sent to {uid}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed: {e}")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_bulkdm_ids':
        ids = [int(x.strip()) for x in text.replace('\n', ',').split(',') if x.strip().isdigit()]
        context.user_data['bulk_ids'] = ids
        context.user_data['admin_state'] = 'awaiting_bulkdm_message'
        await update.message.reply_text(f"Got {len(ids)} IDs. Send the message to broadcast:")
    elif state == 'awaiting_bulkdm_message':
        ids = context.user_data.pop('bulk_ids')
        success = 0
        for uid in ids:
            try:
                await application.bot.send_message(uid, text, parse_mode='HTML')
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"✅ Bulk DM sent to {success}/{len(ids)} users.")
        context.user_data.pop('admin_state', None)
    elif state == 'awaiting_pricing_api':
        api = text.lower()
        if api in ['num', 'tg']:
            context.user_data['pricing_api'] = api
            context.user_data['admin_state'] = 'awaiting_pricing_plan'
            await update.message.reply_text("Which plan? (weekly/monthly):")
        else:
            await update.message.reply_text("Invalid API type. Use 'num' or 'tg'.")
    elif state == 'awaiting_pricing_plan':
        plan = text.lower()
        if plan in ['weekly', 'monthly']:
            context.user_data['pricing_plan'] = plan
            context.user_data['admin_state'] = 'awaiting_pricing_credits'
            await update.message.reply_text("New price in credits:")
        else:
            await update.message.reply_text("Invalid plan. Use 'weekly' or 'monthly'.")
    elif state == 'awaiting_pricing_credits':
        try:
            new_price = int(text)
            api = context.user_data['pricing_api']
            plan = context.user_data['pricing_plan']
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("UPDATE api_plans SET price_credits=? WHERE api_type=? AND plan_name=?", (new_price, api, plan))
                await db.commit()
            await update.message.reply_text(f"✅ Price updated: {api.upper()} {plan} now {new_price} credits.")
            context.user_data.pop('admin_state', None)
        except:
            await update.message.reply_text("Invalid number.")
    elif state == 'awaiting_premium_days':
        days_text = text.lower()
        uid = context.user_data.pop('target_premium_user')
        if days_text == 'permanent':
            await set_premium(uid, days=None)
        else:
            try:
                days = int(days_text)
                await set_premium(uid, days=days)
            except:
                await update.message.reply_text("Invalid number. Cancelled.")
                context.user_data.pop('admin_state', None)
                return
        await update.message.reply_text(f"✅ Premium set for user {uid}.")
        context.user_data.pop('admin_state', None)

# ============================================
# MEDIA BROADCAST HANDLER
# ============================================
async def handle_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    btype = context.user_data.get('broadcast_type')
    if not btype:
        return
    msg = update.message
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE is_banned=0")
        users = [row[0] for row in await cur.fetchall()]
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
    await update.message.reply_text(f"✅ Broadcast sent to {success} users.")

# ============================================
# SELF PING & PREMIUM EXPIRY TASKS
# ============================================
async def self_ping_task():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(SELF_PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as sess:
                await sess.get(f"{RENDER_EXTERNAL_URL}/health")
            await application.bot.get_me()
            logger.info("Self-ping OK")
        except Exception as e:
            logger.warning(f"Ping failed: {e}")

async def premium_expiry_task():
    while True:
        await asyncio.sleep(3600)
        await check_and_update_premium_expiry()

# ============================================
# MAIN STARTUP
# ============================================
async def on_startup():
    global http_session
    http_session = aiohttp.ClientSession()
    await application.initialize()
    await application.bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("buy", "Purchase subscription"),
        BotCommand("balance", "Check credits"),
        BotCommand("redeem", "Redeem code"),
        BotCommand("referral", "Get referral link"),
        BotCommand("admin", "Admin panel")
    ])
    if BOT_MODE == "webhook":
        await application.bot.set_webhook(
            url=f"{RENDER_EXTERNAL_URL}/webhook",
            secret_token=WEBHOOK_SECRET
        )
        logger.info(f"Webhook set to {RENDER_EXTERNAL_URL}/webhook")
    else:
        await application.updater.start_polling()
        logger.info("Polling started.")
    asyncio.create_task(self_ping_task())
    asyncio.create_task(premium_expiry_task())

async def on_shutdown():
    if http_session:
        await http_session.close()
    await application.stop()
    await application.shutdown()

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
application.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^admin_"))
application.add_handler(CallbackQueryHandler(buy_plan_handler, pattern="^plan_"))
application.add_handler(CallbackQueryHandler(gen_specific_key, pattern="^gen_"))
application.add_handler(CallbackQueryHandler(broadcast_type_selected, pattern="^bcast_"))
application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(paginated_user_list, pattern="^userlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_premium_list, pattern="^premiumlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_admin_list, pattern="^adminlist_page_"))
application.add_handler(CallbackQueryHandler(paginated_keys_list, pattern="^keys_page_"))
application.add_handler(CallbackQueryHandler(toggle_ban_handler, pattern="^toggle_ban_"))
application.add_handler(CallbackQueryHandler(add_credits_prompt, pattern="^add_credits_"))
application.add_handler(CallbackQueryHandler(remove_premium_handler, pattern="^remove_premium_"))
application.add_handler(CallbackQueryHandler(make_premium_prompt, pattern="^make_premium_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_broadcast_media))

if __name__ == '__main__':
    import hypercorn.asyncio
    from hypercorn.config import Config
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(on_startup())
    loop.run_until_complete(hypercorn.asyncio.serve(app, config))
