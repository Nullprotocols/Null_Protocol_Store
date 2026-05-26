# database.py - FINAL PRODUCTION VERSION (DYNAMIC PLANS, KEY STATUS, INDEXES)

import asyncpg
import secrets
from datetime import datetime, timedelta, timezone
from config import DATABASE_URL, DEFAULT_PLANS, API_ENDPOINTS

# Global connection pool
pool = None


async def init_db():
    """Initialize database pool, create tables, indexes, and dynamic plans."""
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=30,
        statement_cache_size=100  # prepared statement caching
    )

    async with pool.acquire() as conn:
        # ---------------- USERS TABLE ----------------
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

        # ---------------- API KEYS TABLE ----------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                rate_limit_per_min INTEGER DEFAULT 80,
                total_requests_allowed INTEGER,
                requests_made INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                custom_name TEXT
            )
        """)

        # ---------------- PLANS TABLE ----------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_plans (
                plan_id SERIAL PRIMARY KEY,
                api_type TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                price_credits INTEGER NOT NULL DEFAULT 0,
                duration_days INTEGER NOT NULL,
                UNIQUE(api_type, plan_name)
            )
        """)

        # ---------------- SUBSCRIPTIONS TABLE ----------------
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

        # ---------------- REDEEM CODES TABLE ----------------
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

        # ---------------- CODE REDEMPTIONS TABLE ----------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS code_redemptions (
                redemption_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                code TEXT NOT NULL,
                redeemed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, code)
            )
        """)

        # ---------------- INDEXES (performance) ----------------
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_owner ON users(is_owner)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON api_keys(created_by)
        """)

        # ---------------- INSERT DEFAULT PLANS (existing) ----------------
        for api_type, plans in DEFAULT_PLANS.items():
            for plan_name, details in plans.items():
                await conn.execute("""
                    INSERT INTO api_plans (api_type, plan_name, price_credits, duration_days)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (api_type, plan_name) DO UPDATE
                    SET price_credits = EXCLUDED.price_credits,
                        duration_days = EXCLUDED.duration_days
                """, api_type, plan_name, details['credits'], details['days'])

        # ---------------- DYNAMIC PLANS (for all APIs in config) ----------------
        # Every API gets weekly & monthly plans with price 0 (admin sets later)
        for api_type in API_ENDPOINTS:
            await conn.execute("""
                INSERT INTO api_plans (api_type, plan_name, price_credits, duration_days)
                VALUES ($1, 'weekly', 0, 7)
                ON CONFLICT (api_type, plan_name) DO NOTHING
            """, api_type)
            await conn.execute("""
                INSERT INTO api_plans (api_type, plan_name, price_credits, duration_days)
                VALUES ($1, 'monthly', 0, 30)
                ON CONFLICT (api_type, plan_name) DO NOTHING
            """, api_type)

    print("✅ PostgreSQL tables, indexes & dynamic plans ready (ultra‑fast pool).")


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
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT credits FROM users WHERE user_id=$1", user_id) or 0


async def is_admin(user_id):
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
    expiry = None if days is None else (datetime.now(timezone.utc) + timedelta(days=days))
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_premium=TRUE, premium_expiry=$1 WHERE user_id=$2", expiry, user_id)


async def remove_premium(user_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_premium=FALSE, premium_expiry=NULL WHERE user_id=$1", user_id)


async def set_admin(user_id, status=True):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_owner=$1 WHERE user_id=$2", status, user_id)


async def ban_user(user_id, ban=True):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=$1 WHERE user_id=$2", ban, user_id)


# ====================== API KEY FUNCTIONS ======================
async def generate_random_key():
    return f"ak_{secrets.token_hex(16)}"


async def create_api_key(key, created_by, expires_days=30, rate_limit=80, total_requests=None, custom_name=""):
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


async def get_key_status(key):
    """Return (exists, is_active, is_expired)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active, expires_at FROM api_keys WHERE key=$1", key)
        if not row:
            return False, False, False
        now = datetime.now(timezone.utc)
        is_active = row['is_active'] and (row['expires_at'] > now)
        is_expired = row['expires_at'] < now if row['expires_at'] else False
        return True, is_active, is_expired


async def get_key_owner(key):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT created_by FROM api_keys WHERE key=$1", key)


async def list_api_keys(created_by=None):
    async with pool.acquire() as conn:
        if created_by is not None:
            return await conn.fetch(
                "SELECT key, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, custom_name FROM api_keys WHERE created_by=$1",
                created_by
            )
        return await conn.fetch(
            "SELECT key, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, created_by, custom_name FROM api_keys"
        )


async def deactivate_api_key(key):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active=FALSE WHERE key=$1", key)


async def activate_api_key(key):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active=TRUE WHERE key=$1", key)


async def get_request_stats(key):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT total_requests_allowed, requests_made FROM api_keys WHERE key=$1", key)
        if not row:
            return None, None, None
        total = row['total_requests_allowed']
        used = row['requests_made']
        remaining = None if total is None else max(0, total - used)
        return used, remaining, total


async def increment_request_count(key):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET requests_made = requests_made + 1 WHERE key=$1", key)


# ====================== SUBSCRIPTION FUNCTIONS ======================
async def get_plan(api_type, plan_name):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT plan_id, price_credits, duration_days FROM api_plans WHERE api_type=$1 AND plan_name=$2",
            api_type, plan_name
        )


async def get_all_plans(api_type):
    """Return all plans for a given API type."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT plan_name, price_credits, duration_days FROM api_plans WHERE api_type=$1",
            api_type
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
        if row:
            await conn.execute(
                "UPDATE user_subscriptions SET is_active=FALSE WHERE user_id=$1 AND api_type=$2",
                user_id, api_type
            )
        return False


# ====================== REDEEM CODE FUNCTIONS ======================
async def create_redeem_code(code, credits, created_by, max_uses=1, expires_days=None):
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
        already = await conn.fetchval(
            "SELECT redemption_id FROM code_redemptions WHERE user_id=$1 AND code=$2", user_id, code
        )
        if already:
            return False
        await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id=$2", row['credits_value'], user_id)
        await conn.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=$1", code)
        await conn.execute(
            "INSERT INTO code_redemptions (user_id, code, redeemed_at) VALUES ($1,$2,NOW())", user_id, code
        )
        return True


# ====================== PAGINATION HELPERS ======================
async def count_users():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def get_users_paginated(offset, limit):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, username, first_name, is_banned, is_premium, credits FROM users ORDER BY user_id LIMIT $1 OFFSET $2",
            limit, offset
        )


async def count_admins():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_owner=TRUE")


async def get_admins_paginated(offset, limit):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, username, first_name FROM users WHERE is_owner=TRUE ORDER BY user_id LIMIT $1 OFFSET $2",
            limit, offset
        )


# ====================== BACKUP (CSV EXPORT) ======================
async def export_tables_to_csv():
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
    if pool:
        await pool.close()
        print("✅ PostgreSQL pool closed.")
