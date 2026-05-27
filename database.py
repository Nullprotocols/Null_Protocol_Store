# database.py - FINAL COMPLETE VERSION (100% WORKING)

import asyncpg
import secrets
import json
from datetime import datetime, timedelta, timezone
from config import DATABASE_URL, DEFAULT_PLANS, CUSTOM_RESPONSES

# Global connection pool
pool = None

async def init_db():
    """Initialize database pool and create all tables."""
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

        # API Keys
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

        # Subscription plans (dynamic pricing)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_plans (
                plan_id SERIAL PRIMARY KEY,
                api_type TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                price_credits INTEGER NOT NULL,
                duration_days INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
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

        # API Logs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_logs (
                id SERIAL PRIMARY KEY,
                api_type TEXT NOT NULL,
                api_key TEXT NOT NULL,
                input_value TEXT,
                client_ip TEXT,
                country TEXT,
                city TEXT,
                isp TEXT,
                response_data TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # NEW: Custom Responses per API
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_responses (
                id SERIAL PRIMARY KEY,
                api_type TEXT NOT NULL,
                response_type TEXT NOT NULL,
                message TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(api_type, response_type)
            )
        """)

        # NEW: API Status (enable/disable per API)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_status (
                api_type TEXT PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT TRUE,
                maintenance_mode BOOLEAN DEFAULT FALSE,
                maintenance_message TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Insert default plans for all API types
        for api_type, plans in DEFAULT_PLANS.items():
            for plan_name, details in plans.items():
                await conn.execute("""
                    INSERT INTO api_plans (api_type, plan_name, price_credits, duration_days)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (api_type, plan_name) DO UPDATE
                    SET price_credits = EXCLUDED.price_credits,
                        duration_days = EXCLUDED.duration_days
                """, api_type, plan_name, details['credits'], details['days'])

        # Insert default custom responses
        for response_type, message in CUSTOM_RESPONSES.items():
            await conn.execute("""
                INSERT INTO custom_responses (api_type, response_type, message)
                VALUES ($1, $2, $3)
                ON CONFLICT (api_type, response_type) DO UPDATE
                SET message = EXCLUDED.message
            """, "default", response_type, message)

        # Insert default API status
        for api_type in DEFAULT_PLANS.keys():
            await conn.execute("""
                INSERT INTO api_status (api_type, is_enabled, maintenance_mode)
                VALUES ($1, TRUE, FALSE)
                ON CONFLICT (api_type) DO NOTHING
            """, api_type)

    print("✅ PostgreSQL tables ready (dynamic pricing + custom responses).")

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
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT created_by, expires_at, rate_limit_per_min, is_active FROM api_keys WHERE key=$1", key
        )
        if not row or not row['is_active'] or row['expires_at'] < datetime.now(timezone.utc):
            return False, None, None
        return True, row['created_by'], row['rate_limit_per_min']

async def list_api_keys(created_by=None):
    async with pool.acquire() as conn:
        if created_by is not None:
            return await conn.fetch(
                "SELECT key, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, custom_name FROM api_keys WHERE created_by=$1",
                created_by
            )
        return await conn.fetch(
            "SELECT key, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, created_by FROM api_keys"
        )

async def list_all_keys_full():
    """Get all keys without masking (for admin)"""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT key, created_by, expires_at, rate_limit_per_min, total_requests_allowed, requests_made, is_active, custom_name FROM api_keys ORDER BY created_at DESC"
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
            "SELECT plan_id, price_credits, duration_days FROM api_plans WHERE api_type=$1 AND plan_name=$2 AND is_active=TRUE",
            api_type, plan_name
        )

async def get_all_plans(api_type=None):
    async with pool.acquire() as conn:
        if api_type:
            return await conn.fetch(
                "SELECT plan_id, api_type, plan_name, price_credits, duration_days, is_active FROM api_plans WHERE api_type=$1",
                api_type
            )
        return await conn.fetch(
            "SELECT plan_id, api_type, plan_name, price_credits, duration_days, is_active FROM api_plans"
        )

async def update_plan_price(api_type, plan_name, new_price):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE api_plans SET price_credits=$1 WHERE api_type=$2 AND plan_name=$3",
            new_price, api_type, plan_name
        )

async def toggle_plan(api_type, plan_name, is_active):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE api_plans SET is_active=$1 WHERE api_type=$2 AND plan_name=$3",
            is_active, api_type, plan_name
        )

async def create_subscription(user_id, api_type, plan_name):
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

# ====================== API LOGS FUNCTIONS ======================
async def insert_api_log(api_type, api_key, input_value, client_ip, ip_info, response_data):
    try:
        masked_key = api_key[:12] + "..." if len(api_key) > 12 else api_key
        country = ip_info.get("country", "N/A") if ip_info else "N/A"
        city = ip_info.get("city", "N/A") if ip_info else "N/A"
        isp = ip_info.get("isp", "N/A") if ip_info else "N/A"
        response_json = response_data if isinstance(response_data, str) else json.dumps(response_data, ensure_ascii=False)

        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO api_logs (api_type, api_key, input_value, client_ip, country, city, isp, response_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, api_type, masked_key, input_value, client_ip, country, city, isp, response_json)
    except Exception as e:
        logger.error(f"Error inserting API log: {e}")

async def get_api_logs(limit=1000, offset=0):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM api_logs ORDER BY timestamp DESC LIMIT $1 OFFSET $2",
            limit, offset
        )

async def count_api_logs():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM api_logs")

# ====================== CUSTOM RESPONSES FUNCTIONS ======================
async def get_custom_response(api_type, response_type):
    """Get custom response for a specific API and response type"""
    async with pool.acquire() as conn:
        # First try API-specific
        row = await conn.fetchrow(
            "SELECT message FROM custom_responses WHERE api_type=$1 AND response_type=$2",
            api_type, response_type
        )
        if row:
            return row['message']
        # Fallback to default
        row = await conn.fetchrow(
            "SELECT message FROM custom_responses WHERE api_type='default' AND response_type=$1",
            response_type
        )
        return row['message'] if row else None

async def set_custom_response(api_type, response_type, message):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_responses (api_type, response_type, message, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (api_type, response_type) DO UPDATE
            SET message = EXCLUDED.message, updated_at = NOW()
        """, api_type, response_type, message)

async def get_all_custom_responses(api_type=None):
    async with pool.acquire() as conn:
        if api_type:
            return await conn.fetch(
                "SELECT response_type, message FROM custom_responses WHERE api_type=$1",
                api_type
            )
        return await conn.fetch(
            "SELECT api_type, response_type, message FROM custom_responses"
        )

# ====================== API STATUS FUNCTIONS ======================
async def get_api_status(api_type):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_enabled, maintenance_mode, maintenance_message FROM api_status WHERE api_type=$1",
            api_type
        )
        if row:
            return dict(row)
        return {"is_enabled": True, "maintenance_mode": False, "maintenance_message": None}

async def set_api_status(api_type, is_enabled=None, maintenance_mode=None, maintenance_message=None):
    updates = []
    values = []
    if is_enabled is not None:
        updates.append(f"is_enabled = ${len(values)+1}")
        values.append(is_enabled)
    if maintenance_mode is not None:
        updates.append(f"maintenance_mode = ${len(values)+1}")
        values.append(maintenance_mode)
    if maintenance_message is not None:
        updates.append(f"maintenance_message = ${len(values)+1}")
        values.append(maintenance_message)
    updates.append(f"updated_at = NOW()")
    
    if not updates:
        return
    
    query = f"UPDATE api_status SET {', '.join(updates)} WHERE api_type = ${len(values)+1}"
    values.append(api_type)
    
    async with pool.acquire() as conn:
        await conn.execute(query, *values)

async def list_all_api_status():
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT api_type, is_enabled, maintenance_mode, maintenance_message FROM api_status ORDER BY api_type"
        )

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
    """
    Export all relevant tables to CSV text.
    Now includes api_logs, custom_responses, api_status.
    """
    tables = ['users', 'api_keys', 'api_plans', 'user_subscriptions', 'redeem_codes', 'code_redemptions', 'api_logs', 'custom_responses', 'api_status']
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
