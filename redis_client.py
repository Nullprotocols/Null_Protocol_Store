# redis_client.py - Redis Integration for Ultra-Fast Caching & Rate Limiting

import redis.asyncio as redis
import logging
from config import REDIS_URL, CACHE_TTL

logger = logging.getLogger(__name__)

# Global Redis client
redis_client = None

# In-memory fallback store (used if Redis is unavailable)
_fallback_cache = {}
_fallback_rate = {}


async def init_redis():
    """Initialize Redis connection. If unavailable, fallback to in-memory dict."""
    global redis_client
    if not REDIS_URL:
        logger.warning("⚠️ REDIS_URL not set – using in-memory fallback.")
        return False

    try:
        # Create Redis client with connection pooling
        redis_client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            # Increase timeouts for cloud Redis
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30
        )
        # Test connection
        await redis_client.ping()
        logger.info("✅ Redis connected successfully (Upstash)")
        return True
    except Exception as e:
        logger.warning(f"❌ Redis connection failed: {e}. Falling back to in-memory.")
        redis_client = None
        return False


async def get_cache(key: str) -> str | None:
    """
    Retrieve cached value by key.
    Returns the value if found, else None.
    """
    if redis_client:
        try:
            return await redis_client.get(key)
        except Exception as e:
            logger.debug(f"Redis get error: {e}")

    # Fallback to in-memory
    return _fallback_cache.get(key)


async def set_cache(key: str, value: str, ttl: int = CACHE_TTL):
    """
    Store a value in cache with expiration (seconds).
    """
    if redis_client:
        try:
            await redis_client.setex(key, ttl, value)
            return
        except Exception as e:
            logger.debug(f"Redis set error: {e}")

    # Fallback to in-memory (no TTL in simple dict, we just store)
    _fallback_cache[key] = value
    # Note: In-memory fallback does not support expiration automatically.
    # In main code, get_cached will also check time-based expiry separately.


async def incr_rate_limit(key: str, window: int = 60) -> int | None:
    """
    Increment a rate limit counter for the given key.
    Sets expiration on first increment.
    Returns the current count. If Redis unavailable, returns None (caller handles fallback).
    """
    if redis_client:
        try:
            current = await redis_client.incr(key)
            if current == 1:
                await redis_client.expire(key, window)
            return current
        except Exception as e:
            logger.debug(f"Redis incr error: {e}")

    # Fallback: cannot guarantee atomicity, so return None to signal caller to use in-memory tracking
    return None


async def delete_key(key: str):
    """Delete a key from cache."""
    if redis_client:
        try:
            await redis_client.delete(key)
        except:
            pass


async def close_redis():
    """Close the Redis connection gracefully."""
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed.")
