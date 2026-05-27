# database.py - FINAL ASYNCPG VERSION (ULTRA FAST, ALL FEATURES, NO ERRORS)

import asyncpg
import secrets
from datetime import datetime, timedelta, timezone
from config import DATABASE_URL, DEFAULT_PLANS

# Global connection pool – optimized for speed
pool = None

async def init_db():
    """Initialize database pool (5-20 connections) and create all tables."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)

    async with pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned BOOLEAN DEFAULT FALSE,
                is_owner BOOLEAN DEFAULT FALSE,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                referrer_id BIGINT,
                credits INTEGER DEFAULT 0,
                is_premium BOOLEAN DEFAULT FALSE,
                premium_expiry TIMESTAMPTZ,
                joined_force_channels BOOLEAN DEFAULT FALSE
            )
        """)

        # API Keys (with request tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                rate_limit_per_min INTEGER DEFAULT 80,
                total_requests_allowed INTEGER,          -- NULL = unlimited
                requests_made INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                custom_name TEXT
            )
        """)

        # Subscription plans
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_plans (
                plan_id SERIAL PRIMARY KEY,
                api_type TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                price_credits INTEGER NOT NULL,
                duration_days INTEGER NOT NULL,
                UNIQUE(api_type, plan_name)
            )
        """)

        # User subscriptions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                sub_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                api_type TEXT NOT NULL,
                plan_id INTEGER NOT NULL,
                start_date TIMESTAMPTZ DEFAULT NOW(),
                end_date TIMESTAMPTZ NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(plan_id) REFERENCES api_plans(plan_id)
            )
        """)

        # Redeem codes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                credits_value INTEGER NOT NULL,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)

        # Code redemptions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS code_redemptions (
                redemption_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                code TEXT NOT NULL,
                redeemed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, code)
            )
        """)

        # Insert/update default plans for ALL APIs
        for api_type, plans in DEFAULT_PLANS.items():
            for plan_name, details in plans.items():
                await conn.execute("""
                    INSERT INTO api_plans (api_type, plan_name, price_credits, duration_days)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (api_type, plan_name) DO UPDATE
                    SET price_credits = EXCLUDED.price_credits,
                        duration_days = EXCLUDED.duration_days
                """, api_type, plan_name, details['credits'], details['days'])

    print("✅ PostgreSQL tables & plans ready (ultra‑fast pool).")

# ====================== USER FUNCTIONS ======================
async def get_user(user_id: int):
    """Return user dict; create if not exists."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not row:
            now = datetime.now(timezone.utc)
            await conn.execute(
                "INSERT INTO users (user_id, joined_at, credits) VALUES ($1, $2, 0) ON CONFLICT DO NOTHING",
                user_id, now
            )
            return {
                "user_id": user_id,
                "username": None,
                "first_name": None,
                "last_name": None,
                "is_banned": False,
                "is_owner": False,
                "joined_at": now.isoformat(),
                "referrer_id": None,
                "credits": 0,
                "is_premium": False,
                "premium_expiry": None
            }
        return dict(row)

async def update_user_info(user_id, username, first_name, last_name):
    """Update Telegram profile info."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET username=$1, first_name=$2, last_name=$3 WHERE user_id=$4",
            username, first_name, last_name, user_id
        )

async def set_referrer(user_id, referrer_id):
    """Set referrer if not already set. Returns True on success."""
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT referrer_id FROM users WHERE user_id=$1", user_id)
        if existing is None and referrer_id != user_id:
            await conn.execute("UPDATE users SET referrer_id=$1 WHERE user_id=$2", referrer_id, user_id)
            return True
        return False

async def add_credits(user_id, amount):
    """Add credits to user."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id=$2", amount, user_id)

async def deduct_credits(user_id, amount) -> bool:
    """Deduct credits if sufficient balance. Returns True if successful."""
    async with pool.acquire() as conn:
        credits = await conn.fetchval("SELECT credits FROM users WHERE user_id=$1", user_id)
        if credits is not None and credits >= amount:
            await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id=$2", amount, user_id)
            return True
        return False

async def get_user_credits(user_id):
    """Get current credit balance."""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT credits FROM users WHERE user_id=$1", user_id) or 0

async def is_admin(user_id):
    """Check if user is owner (admin). Owner ID is super admin."""
    from config import OWNER_ID
    if user_id == OWNER_ID:
        return True
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT is_owner FROM users WHERE user_id=$1", user_id) or False

async def is_premium(user_id):
    """Check if user has active premium; auto-expire if needed."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_premium, premium_expiry FROM users WHERE user_id=$1", user_id)
        if not row or not row['is_premium']:
            return False
        if row['premium_expiry'] and row['premium_expiry'] < datetime.now(timezone.utc):
            await conn.execute("UPDATE users SET is_premium=FALSE WHERE user_id=$1", user_id)
            return False
        return True

async def set_premium(user_id, days=None):
    """Grant premium for given days (None = permanent)."""
    expiry = None if days is None else (datetime.now(timezone.utc) + timedelta(days=days))
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_premium=TRUE, premium_expiry=$1 WHERE user_id=$2", expiry, user_id)

async def remove_premium(user_id):
    """Remove premium status."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_premium=FALSE, premium_expiry=NULL WHERE user_id=$1", user_id)

async def set_admin(user_id, status=True):
    """Promote/demote admin (owner flag)."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_owner=$1 WHERE user_id=$2", status, user_id)

async def ban_user(user_id, ban=True):
    """Ban or unban a user."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=$1 WHERE user_id=$2", ban, user_id)

# ====================== API KEY FUNCTIONS ======================
async def generate_random_key():
    """Generate a random API key string."""
    return f"ak_{secrets.token_hex(16)}"

async def create_api_key(key, created_by, expires_days=30, rate_limit=80, total_requests=None, custom_name=""):
    """Create a new API key with custom limits (uses timezone‑aware dates)."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO api_keys (key, created_by, created_at, expires_at, rate_limit_per_min, total_requests_allowed, is_active, custom_name)
            VALUES ($1, $2, NOW(), $3, $4, $5, TRUE, $6)
            ON CONFLICT (key) DO NOTHING
        """, key, created_by, expires_at, rate_limit, total_requests, custom_name)

async def validate_api_key(key):
    """Return (valid, created_by, rate_limit). Checks expiry and active status."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT created_by, expires_at, rate_limit_per_min, is_active FROM api_keys WHERE key=$1", key
        )
        if not row or not row['is_active'] or row['expires_at'] < datetime.now(timezone.utc):
            return False, None, None
        return True, row['created_by'], row['rate_limit_per_min']

async def list_api_keys(created_by=None):
    """Return list of key rows (dicts). If created_by provided, filter by that user."""
    async with pool.acquire() as conn:
        if created_by is not None:
            return await conn.fetch(
                "SELECT key, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, custom_name FROM api_keys WHERE created_by=$1",
                created_by
            )
        return await conn.fetch(
            "SELECT key, created_by, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, custom_name FROM api_keys"
        )

async def deactivate_api_key(key):
    """Set key inactive."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active=FALSE WHERE key=$1", key)

async def activate_api_key(key):
    """Set key active."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active=TRUE WHERE key=$1", key)

async def get_request_stats(key):
    """Return (used, remaining, total) for a key. remaining is None if unlimited."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT total_requests_allowed, requests_made FROM api_keys WHERE key=$1", key)
        if not row:
            return None, None, None
        total = row['total_requests_allowed']
        used = row['requests_made']
        remaining = None if total is None else max(0, total - used)
        return used, remaining, total

async def increment_request_count(key):
    """Increment request counter for the key."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET requests_made = requests_made + 1 WHERE key=$1", key)

# ====================== SUBSCRIPTION FUNCTIONS ======================
async def get_plan(api_type, plan_name):
    """Get plan details (plan_id, price_credits, duration_days)."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT plan_id, price_credits, duration_days FROM api_plans WHERE api_type=$1 AND plan_name=$2",
            api_type, plan_name
        )

async def create_subscription(user_id, api_type, plan_name):
    """Activate a plan (deduct credits, insert subscription). Returns True on success."""
    plan = await get_plan(api_type, plan_name)
    if not plan:
        return False
    plan_id, price, days = plan
    if not await deduct_credits(user_id, price):
        return False
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_subscriptions (user_id, api_type, plan_id, start_date, end_date, is_active) VALUES ($1,$2,$3,$4,$5,TRUE)",
            user_id, api_type, plan_id, start, end
        )
    return True

async def has_active_subscription(user_id, api_type):
    """Check if user has an active (non-expired) subscription for an API type."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT end_date FROM user_subscriptions WHERE user_id=$1 AND api_type=$2 AND is_active=TRUE",
            user_id, api_type
        )
        if row and row['end_date'] > datetime.now(timezone.utc):
            return True
        # Mark as inactive if expired
        if row:
            await conn.execute(
                "UPDATE user_subscriptions SET is_active=FALSE WHERE user_id=$1 AND api_type=$2",
                user_id, api_type
            )
        return False

# ====================== REDEEM CODE FUNCTIONS ======================
async def create_redeem_code(code, credits, created_by, max_uses=1, expires_days=None):
    """Create a new redeem code."""
    expires = None if expires_days is None else (datetime.now(timezone.utc) + timedelta(days=expires_days))
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO redeem_codes (code, credits_value, created_by, created_at, expires_at, max_uses) VALUES ($1,$2,$3,NOW(),$4,$5)",
            code, credits, created_by, expires, max_uses
        )

async def redeem_code(user_id, code):
    """Redeem a code for credits. Returns True on success."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits_value, max_uses, used_count, expires_at, is_active FROM redeem_codes WHERE code=$1", code
        )
        if not row or not row['is_active'] or row['used_count'] >= row['max_uses']:
            return False
        if row['expires_at'] and row['expires_at'] < datetime.now(timezone.utc):
            return False
        # Check if user already used this code
        already = await conn.fetchval(
            "SELECT redemption_id FROM code_redemptions WHERE user_id=$1 AND code=$2", user_id, code
        )
        if already:
            return False
        # Add credits, increment used count, record redemption
        await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id=$2", row['credits_value'], user_id)
        await conn.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=$1", code)
        await conn.execute(
            "INSERT INTO code_redemptions (user_id, code, redeemed_at) VALUES ($1,$2,NOW())", user_id, code
        )
        return True

# ====================== PAGINATION HELPERS ======================
async def count_users():
    """Total number of users."""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")

async def get_users_paginated(offset, limit):
    """Return list of user dicts for admin panel (paginated)."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, username, first_name, is_banned, is_premium, credits FROM users ORDER BY user_id LIMIT $1 OFFSET $2",
            limit, offset
        )

async def count_admins():
    """Total number of admins."""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_owner=TRUE")

async def get_admins_paginated(offset, limit):
    """Return list of admin dicts."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, username, first_name FROM users WHERE is_owner=TRUE ORDER BY user_id LIMIT $1 OFFSET $2",
            limit, offset
        )

# ====================== BACKUP (CSV EXPORT) ======================
async def export_tables_to_csv():
    """
    Export all relevant tables to CSV text.
    Returns dict: table_name -> CSV string.
    """
    tables = ['users', 'api_keys', 'api_plans', 'user_subscriptions', 'redeem_codes', 'code_redemptions']
    csv_files = {}
    async with pool.acquire() as conn:
        for table in tables:
            rows = await conn.fetch(f"SELECT * FROM {table}")
            if not rows:
                csv_files[table] = ""
                continue
            headers = list(rows[0].keys())
            lines = [','.join(headers)]
            for row in rows:
                values = [str(row[h]).replace(",", "\\,") if row[h] is not None else "" for h in headers]
                lines.append(','.join(values))
            csv_files[table] = '\n'.join(lines)
    return csv_files

# ====================== CLEANUP ======================
async def close_db():
    """Close the asyncpg connection pool."""
    if pool:
        await pool.close()
        print("✅ PostgreSQL pool closed.")
