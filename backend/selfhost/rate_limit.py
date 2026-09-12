from functools import lru_cache

from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError

from selfhost.config import settings


@lru_cache
def redis():
    return Redis.from_url(
        settings().redis_url, socket_timeout=3, socket_connect_timeout=3
    )


def limit(key, maximum, seconds):
    try:
        count = redis().eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1,
            "ollomi:" + key,
            seconds,
        )
    except RedisError:
        raise HTTPException(503, "Authentication rate limiter unavailable") from None
    if count > maximum:
        raise HTTPException(
            429, "Too many attempts", headers={"Retry-After": str(seconds)}
        )
