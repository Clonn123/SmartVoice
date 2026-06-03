# app/core/redis_lock.py

import redis
import uuid

redis_client = redis.Redis(host="redis", port=6379, db=0)


def lock_key(phone: str) -> str:
    return f"lock:call:{phone}"


def acquire_lock(phone: str, ttl: int = 120) -> str | None:
    token = str(uuid.uuid4())

    ok = redis_client.set(
        lock_key(phone),
        token,
        nx=True,
        ex=ttl,
    )

    return token if ok else None


def release_lock(phone: str, token: str):
    script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """

    redis_client.eval(script, 1, lock_key(phone), token)
