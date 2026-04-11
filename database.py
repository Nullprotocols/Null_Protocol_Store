# database.py - ASYNC VERSION WITH ALL FEATURES (RENDER READY)

import sqlite3
import secrets
import asyncio
import aiosqlite
from datetime import datetime, timedelta
from config import DB_FILE, DEFAULT_PLANS, REFERRAL_REWARD_CREDITS

# ============================================
# 1. SYNC CONNECTION (For backward compatibility, use with caution)
# ============================================
sync_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
sync_c = sync_conn.cursor()

# ============================================
# 2. DATABASE SETUP (Create Tables if not exist)
# ============================================
def init_db_sync():
    """Synchronous initialization (called once at startup)"""
    # Users table
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_banned INTEGER DEFAULT 0,
            is_owner INTEGER DEFAULT 0,
            joined_at TEXT,
            referrer_id INTEGER,
            credits INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            joined_force_channels INTEGER DEFAULT 0
        )
    ''')

    # Try to add new columns if they don't exist (migration safe)
    try:
        sync_c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    except:
        pass
    try:
        sync_c.execute("ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT 0")
    except:
        pass
    try:
        sync_c.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
    except:
        pass
    try:
        sync_c.execute("ALTER TABLE users ADD COLUMN premium_expiry TEXT")
    except:
        pass
    try:
        sync_c.execute("ALTER TABLE users ADD COLUMN joined_force_channels INTEGER DEFAULT 0")
    except:
        pass

    # API Keys table
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            created_by INTEGER,
            created_at TEXT,
            expires_at TEXT,
            rate_limit_per_min INTEGER DEFAULT 80,
            is_active INTEGER DEFAULT 1,
            custom_name TEXT
        )
    ''')

    # API Plans table (pricing)
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS api_plans (
            plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_type TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            price_credits INTEGER NOT NULL,
            duration_days INTEGER NOT NULL,
            UNIQUE(api_type, plan_name)
        )
    ''')

    # User Subscriptions table
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            sub_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            api_type TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(plan_id) REFERENCES api_plans(plan_id)
        )
    ''')

    # Redeem Codes table
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            credits_value INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Code Redemptions table (track who used which code)
    sync_c.execute('''
        CREATE TABLE IF NOT EXISTS code_redemptions (
            redemption_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            redeemed_at TEXT NOT NULL,
            UNIQUE(user_id, code)
        )
    ''')

    sync_conn.commit()

    # Insert default plans from config if not exist
    for api_type, plans in DEFAULT_PLANS.items():
        for plan_name, details in plans.items():
            sync_c.execute('''
                INSERT OR IGNORE INTO api_plans (api_type, plan_name, price_credits, duration_days)
                VALUES (?, ?, ?, ?)
            ''', (api_type, plan_name, details['credits'], details['days']))
    sync_conn.commit()

    print("✅ Database tables initialized/updated.")

# Call sync init at module load
init_db_sync()

# ============================================
# 3. ASYNC DATABASE CONNECTION (For production)
# ============================================
async def get_db():
    """Return an async database connection with WAL mode enabled."""
    db = await aiosqlite.connect(DB_FILE)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA cache_size=-20000")  # 20MB cache
    return db

# ============================================
# 4. USER HELPER FUNCTIONS (ASYNC)
# ============================================
async def get_user(user_id: int):
    """Get user as dict, create if not exists."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, last_name, is_banned, is_owner, joined_at, referrer_id, credits, is_premium, premium_expiry FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            now = datetime.now().isoformat()
            await db.execute(
                "INSERT INTO users (user_id, joined_at, credits) VALUES (?, ?, ?)",
                (user_id, now, 0)
            )
            await db.commit()
            return {
                "user_id": user_id,
                "username": None,
                "first_name": None,
                "last_name": None,
                "is_banned": 0,
                "is_owner": 0,
                "joined_at": now,
                "referrer_id": None,
                "credits": 0,
                "is_premium": 0,
                "premium_expiry": None
            }
        return {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "is_banned": row[4],
            "is_owner": row[5],
            "joined_at": row[6],
            "referrer_id": row[7],
            "credits": row[8] if row[8] is not None else 0,
            "is_premium": row[9] if len(row) > 9 else 0,
            "premium_expiry": row[10] if len(row) > 10 else None
        }

async def update_user_info(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Update user profile info."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE users SET username=?, first_name=?, last_name=? WHERE user_id=?",
            (username, first_name, last_name, user_id)
        )
        await db.commit()

async def set_referrer(user_id: int, referrer_id: int):
    """Set referrer for a user (if not already set)."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0] is None:
            await db.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (referrer_id, user_id))
            await db.commit()
            return True
        return False

async def add_credits(user_id: int, amount: int):
    """Add credits to user account."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def deduct_credits(user_id: int, amount: int) -> bool:
    """Deduct credits if user has sufficient balance. Returns True if success."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0] >= amount:
            await db.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (amount, user_id))
            await db.commit()
            return True
        return False

async def get_user_credits(user_id: int) -> int:
    """Get current credit balance."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def is_admin(user_id: int) -> bool:
    """Check if user is owner or added admin."""
    from config import OWNER_ID
    if user_id == OWNER_ID:
        return True
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT is_owner FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        return row is not None and row[0] == 1

async def is_premium(user_id: int) -> bool:
    """Check if user has active premium."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            return False
        if row[1] is not None:
            expiry = datetime.fromisoformat(row[1])
            if expiry < datetime.now():
                # Premium expired
                await db.execute("UPDATE users SET is_premium=0 WHERE user_id=?", (user_id,))
                await db.commit()
                return False
        return True

async def set_premium(user_id: int, days: int = None):
    """Make user premium for given days (None = permanent)."""
    async with aiosqlite.connect(DB_FILE) as db:
        expiry = None if days is None else (datetime.now() + timedelta(days=days)).isoformat()
        await db.execute(
            "UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=?",
            (expiry, user_id)
        )
        await db.commit()

async def remove_premium(user_id: int):
    """Remove premium status."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE user_id=?", (user_id,))
        await db.commit()

async def get_all_premium_users():
    """List all premium users (active)."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, premium_expiry FROM users WHERE is_premium=1"
        )
        return await cursor.fetchall()

async def check_and_update_premium_expiry():
    """Background task: deactivate expired premium."""
    async with aiosqlite.connect(DB_FILE) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE users SET is_premium=0 WHERE is_premium=1 AND premium_expiry IS NOT NULL AND premium_expiry < ?",
            (now,)
        )
        await db.commit()

# ============================================
# 5. API KEY FUNCTIONS (ASYNC)
# ============================================
async def generate_random_key():
    return f"ak_{secrets.token_hex(16)}"

async def create_api_key(key: str, created_by: int, expires_days: int = 30, rate_limit: int = 80, custom_name: str = ""):
    async with aiosqlite.connect(DB_FILE) as db:
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
        created_at = datetime.now().isoformat()
        await db.execute(
            "INSERT OR REPLACE INTO api_keys (key, created_by, created_at, expires_at, rate_limit_per_min, is_active, custom_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, created_by, created_at, expires_at, rate_limit, 1, custom_name)
        )
        await db.commit()

async def validate_api_key(key: str):
    """Returns (valid, created_by, rate_limit)"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT created_by, expires_at, rate_limit_per_min, is_active FROM api_keys WHERE key=?",
            (key,)
        )
        row = await cursor.fetchone()
        if not row:
            return False, None, None
        created_by, expires_at, rate_limit, is_active = row
        if not is_active or datetime.now() > datetime.fromisoformat(expires_at):
            return False, None, None
        return True, created_by, rate_limit

async def list_api_keys(created_by: int = None):
    async with aiosqlite.connect(DB_FILE) as db:
        if created_by:
            cursor = await db.execute(
                "SELECT key, expires_at, rate_limit_per_min, custom_name, is_active FROM api_keys WHERE created_by=?",
                (created_by,)
            )
        else:
            cursor = await db.execute(
                "SELECT key, expires_at, rate_limit_per_min, custom_name, is_active, created_by FROM api_keys"
            )
        return await cursor.fetchall()

# ============================================
# 6. SUBSCRIPTION FUNCTIONS (ASYNC)
# ============================================
async def get_plan(api_type: str, plan_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT plan_id, price_credits, duration_days FROM api_plans WHERE api_type=? AND plan_name=?",
            (api_type, plan_name)
        )
        return await cursor.fetchone()

async def create_subscription(user_id: int, api_type: str, plan_name: str):
    """Create subscription after deducting credits (caller should check balance)."""
    plan = await get_plan(api_type, plan_name)
    if not plan:
        return False
    plan_id, price, days = plan
    # Deduct credits
    if not await deduct_credits(user_id, price):
        return False
    start = datetime.now().isoformat()
    end = (datetime.now() + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, api_type, plan_id, start, end, 1)
        )
        await db.commit()
    return True

async def has_active_subscription(user_id: int, api_type: str) -> bool:
    """Check if user has an active subscription for given API type."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT end_date FROM user_subscriptions WHERE user_id=? AND api_type=? AND is_active=1",
            (user_id, api_type)
        )
        row = await cursor.fetchone()
        if row:
            end = datetime.fromisoformat(row[0])
            if end > datetime.now():
                return True
            else:
                # Optionally mark inactive
                await db.execute(
                    "UPDATE user_subscriptions SET is_active=0 WHERE user_id=? AND api_type=?",
                    (user_id, api_type)
                )
                await db.commit()
        return False

# ============================================
# 7. REDEEM CODE FUNCTIONS (ASYNC)
# ============================================
async def create_redeem_code(code: str, credits: int, created_by: int, max_uses: int = 1, expires_days: int = None):
    expires = None if expires_days is None else (datetime.now() + timedelta(days=expires_days)).isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO redeem_codes (code, credits_value, created_by, created_at, expires_at, max_uses) VALUES (?, ?, ?, ?, ?, ?)",
            (code, credits, created_by, datetime.now().isoformat(), expires, max_uses)
        )
        await db.commit()

async def redeem_code(user_id: int, code: str) -> bool:
    """Redeem code, add credits to user. Returns True if successful."""
    async with aiosqlite.connect(DB_FILE) as db:
        # Check code validity
        cursor = await db.execute(
            "SELECT credits_value, max_uses, used_count, expires_at, is_active FROM redeem_codes WHERE code=?",
            (code,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        value, max_uses, used, expires, active = row
        if not active:
            return False
        if used >= max_uses:
            return False
        if expires and datetime.now() > datetime.fromisoformat(expires):
            return False

        # Check if user already used this code
        cursor = await db.execute(
            "SELECT redemption_id FROM code_redemptions WHERE user_id=? AND code=?",
            (user_id, code)
        )
        if await cursor.fetchone():
            return False

        # All good, add credits, increment used count, record redemption
        await db.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (value, user_id))
        await db.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?", (code,))
        await db.execute(
            "INSERT INTO code_redemptions (user_id, code, redeemed_at) VALUES (?, ?, ?)",
            (user_id, code, datetime.now().isoformat())
        )
        await db.commit()
        return True

# ============================================
# 8. PAGINATION HELPERS (ASYNC)
# ============================================
async def count_users():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_users_paginated(offset: int, limit: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, is_banned, is_premium, credits FROM users ORDER BY user_id LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return await cursor.fetchall()

async def get_admins_paginated(offset: int, limit: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name FROM users WHERE is_owner=1 ORDER BY user_id LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return await cursor.fetchall()

async def count_admins():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_owner=1")
        row = await cursor.fetchone()
        return row[0] if row else 0

# ============================================
# 9. SYNC WRAPPER FUNCTIONS (For easy migration)
# ============================================
def get_user_sync(user_id):
    """Synchronous version for compatibility."""
    sync_c.execute("SELECT user_id, username, first_name, last_name, is_banned, is_owner, joined_at, referrer_id, credits, is_premium, premium_expiry FROM users WHERE user_id=?", (user_id,))
    row = sync_c.fetchone()
    if not row:
        now = datetime.now().isoformat()
        sync_c.execute("INSERT INTO users (user_id, joined_at, credits) VALUES (?, ?, ?)", (user_id, now, 0))
        sync_conn.commit()
        return {"user_id": user_id, "credits": 0, "is_banned": 0, "is_owner": 0, "is_premium": 0}
    return {
        "user_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "is_banned": row[4],
        "is_owner": row[5],
        "joined_at": row[6],
        "referrer_id": row[7],
        "credits": row[8] if row[8] is not None else 0,
        "is_premium": row[9] if len(row) > 9 else 0,
        "premium_expiry": row[10] if len(row) > 10 else None
    }

def is_admin_sync(user_id):
    from config import OWNER_ID
    if user_id == OWNER_ID:
        return True
    sync_c.execute("SELECT is_owner FROM users WHERE user_id=?", (user_id,))
    res = sync_c.fetchone()
    return res is not None and res[0] == 1

def create_api_key_sync(key, created_by, expires_days=30, rate_limit=80, custom_name=""):
    expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
    sync_c.execute(
        "INSERT OR REPLACE INTO api_keys (key, created_by, created_at, expires_at, rate_limit_per_min, is_active, custom_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, created_by, datetime.now().isoformat(), expires_at, rate_limit, 1, custom_name)
    )
    sync_conn.commit()

def list_api_keys_sync(created_by=None):
    if created_by:
        sync_c.execute("SELECT key, expires_at, rate_limit_per_min, custom_name, is_active FROM api_keys WHERE created_by=?", (created_by,))
    else:
        sync_c.execute("SELECT key, expires_at, rate_limit_per_min, custom_name, is_active, created_by FROM api_keys")
    return sync_c.fetchall()

# ============================================
# 10. CLOSE CONNECTION (Call on shutdown)
# ============================================
async def close_db():
    # aiosqlite connections are context managed, but close sync if needed
    sync_conn.close()
    print("✅ Database connections closed.")

# ============================================
print("✅ Database module loaded (async ready).")
