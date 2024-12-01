import redis
import logging
from .exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_host: str, redis_port: int,
                 time_window_sec: int, allowed_requests: int):
        self.__redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        logger.info(
            f"Redis connection estabilished with {redis_host}:{redis_port}"
        )
        self.__key_prefix = f"rl-{id(self)}-"
        self.__time_window_sec = time_window_sec
        self.__allowed_requests = allowed_requests
        logger.info(
            "Rate Limiter initialised:- "
            f"Key prefix: {self.__key_prefix}, "
            f"Time window: {self.__time_window_sec}, "
            f"Allowed requests in each window: {self.__allowed_requests}"
        )
        return

    def __del__(self) -> None:
        if self.__redis_client:
            self.__redis_client.close()
            logger.debug(
                f"Redis connection closed by RateLimiter with id {id(self)}"
            )

    def __get_prefixed_key(self, key: str) -> str:
        return self.__key_prefix + key

    def count(self, key) -> None:
        logger.debug(f"Counting a request for key {key}")
        pfx_key = self.__get_prefixed_key(key)
        logger.debug(f"Key:{key}, Prefixed-key:{pfx_key}")
        if self.__redis_client.exists(pfx_key):
            current_count = int(self.__redis_client.get(pfx_key))
            logger.debug(
                f"Requests count for key '{pfx_key}' "
                f"in current window: {current_count}"
            )

            if current_count >= self.__allowed_requests:
                raise RateLimitExceededException

            self.__redis_client.set(
                name=pfx_key,
                value=(current_count + 1),
                keepttl=True
            )
        else:
            logger.debug(
                f"Requests count for key '{pfx_key}' "
                "in current window: 0"
            )
            self.__redis_client.set(
                name=pfx_key,
                value=1,
                ex=self.__time_window_sec
            )
        return
