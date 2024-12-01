import time
import redis
import pickle
from typing import Callable
from enum import Enum
from utils import RateLimiter
import logging
import hashlib

logger = logging.getLogger(__name__)


class BuildState(Enum):
    PENDING = 0
    RUNNING = 1
    SUCCESS = 2
    FAILURE = 3
    ERROR = 4


class BuildProgress:
    def __init__(
        self,
        state: BuildState,
        percent: int
    ) -> None:
        self.state = state
        self.percent = percent


class BuildInfo:
    def __init__(self,
                 vehicle: str,
                 remote: str,
                 git_hash: str,
                 selected_features: list) -> None:
        self.vehicle = vehicle
        self.remote = remote
        self.git_hash = git_hash
        self.selected_features = selected_features
        self.progress = BuildProgress(
            state=BuildState.PENDING,
            percent=0
        )
        self.time_created = time.time()


class BuildManager:

    __singleton = None

    def __init__(self,
                 outdir: str,
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 redis_announce_channel: str = 'builds-channel') -> None:
        # Enforce singleton pattern by raising an error if
        # an instance already exists.
        if BuildManager.__singleton:
            raise RuntimeError("BuildManager must be a singleton")

        self.__redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=False
        )
        self.__pubsub = self.__redis_client.pubsub(
            ignore_subscribe_messages=True
        )
        self.__redis_channel = redis_announce_channel
        self.__pubsub.subscribe(self.__redis_channel)
        self.__outdir = outdir
        self.__ip_rate_limiter = RateLimiter(
            redis_host=redis_host,
            redis_port=redis_port,
            time_window_sec=3600,
            allowed_requests=3
        )
        self.__build_entry_prefix = "buildmeta-"
        logger.info(
            "Build Manager initialised:- "
            f"Redis host: {redis_host}, "
            f"Redis port: {redis_port}, "
            f"Redis channel: {self.__redis_channel}, "
            f"Build Output Directory: {self.__outdir}, "
            f"Build entry prefix: {self.__build_entry_prefix}"
        )
        BuildManager.__singleton = self

    def __del__(self) -> None:
        if self.__redis_client:
            logger.debug("Redis connection closed")
            self.__redis_client.close()

    def __key_from_build_id(self, build_id: str):
        return self.__build_entry_prefix + build_id

    def __build_id_from_key(self, key: str):
        return key[len(self.__build_entry_prefix):]

    def get_outdir(self) -> str:
        return self.__outdir

    def __generate_build_id(self, build_info: BuildInfo) -> str:
        token = hashlib.sha256(
            f"{build_info}-{time.time_ns()}".encode()
        ).hexdigest()
        return token

    def submit_build(self,
                     build_info: BuildInfo,
                     client_ip: str) -> str:
        self.__ip_rate_limiter.count(client_ip)
        build_id = self.__generate_build_id(build_info)
        self.__add_build_info(build_id=build_id, build_info=build_info)
        self.__announce_build(build_id=build_id)
        return build_id

    def __announce_build(self,
                         build_id: str) -> None:
        self.__redis_client.publish(
            channel=self.__redis_channel,
            message=build_id
        )

    def listen_build_announcements(
            self,
            callback: Callable[..., object]
    ) -> None:
        for message in self.__pubsub.listen():
            logger.debug(f"Listening channels: {self.__pubsub.channels()}")
            if message['type'] == 'message':
                logger.debug(
                    f"Received message on pub/sub channel, "
                    f"message: {message['data']}"
                )
                build_id = message['data']
                logger.debug(f"Calling {callback}")
                callback(build_id)

    def build_exists(self,
                     build_id: str) -> bool:
        return self.__redis_client.exists(
            self.__key_from_build_id(build_id=build_id)
        )

    def __add_build_info(self,
                         build_id: str,
                         build_info: BuildInfo,
                         ttl_sec: int = 86400) -> None:
        if self.build_exists(build_id=build_id):
            raise ValueError(f"Build with id {build_id} already exists")

        key = self.__key_from_build_id(build_id)
        logger.debug(
            "Adding build info, "
            f"Redis key: {key}, "
            f"Build Info: {build_info}, "
            f"TTL: {ttl_sec} sec"
        )
        self.__redis_client.set(
            name=key,
            value=pickle.dumps(build_info),
            ex=ttl_sec
        )

    def get_build_info(self,
                       build_id: str) -> BuildInfo:
        key = self.__key_from_build_id(build_id=build_id)
        logger.debug(
            f"Getting build info for build id {build_id}, Redis Key: {key}"
        )
        value = self.__redis_client.get(key)
        logger.debug(f"Got value {value} at key {key}")
        return pickle.loads(value) if value else None

    def __update_build_progress(self,
                                build_id: str,
                                progress: BuildProgress) -> None:
        build_info = self.get_build_info(build_id=build_id)
        logger.debug(f"Existing Build info: {build_info}")
        build_info.progress = progress
        logger.debug(f"New progress: {progress}")
        self.__redis_client.set(
            name=self.__key_from_build_id(build_id=build_id),
            value=pickle.dumps(build_info),
            keepttl=True
        )

    def update_build_progress_percent(self,
                                      build_id: str,
                                      percent: int) -> None:
        state = self.get_build_info(build_id=build_id).progress.state
        progress = BuildProgress(
            percent=percent,
            state=state
        )
        self.__update_build_progress(
            build_id=build_id,
            progress=progress
        )

    def update_build_progress_state(self,
                                    build_id: str,
                                    new_state: BuildState) -> None:
        percent = self.get_build_info(build_id=build_id).progress.percent
        progress = BuildProgress(
            percent=percent,
            state=new_state
        )
        self.__update_build_progress(
            build_id=build_id,
            progress=progress
        )

    def get_all_build_ids(self) -> list:
        keys_encoded = self.__redis_client.keys(
            f"{self.__build_entry_prefix}*"
        )
        keys = [key.decode() for key in keys_encoded]
        logger.debug(
            f"Keys with prefix {self.__build_entry_prefix}"
            f": {keys}"
        )
        return [
            self.__build_id_from_key(key)
            for key in keys
        ]

    def get_running_build_ids(self) -> list:
        ret = []
        for build_id in self.get_all_build_ids():
            info = self.get_build_info(build_id=build_id)
            logger.debug(f"Build {build_id} State: {info.progress.state.name}")
            if info.progress.state == BuildState.RUNNING:
                ret.append(build_id)
        return ret

    def get_artifacts_fileaname_for_build(self, build_id: str) -> str:
        return build_id + ".zip"

    @staticmethod
    def get_singleton() -> "BuildManager":
        return BuildManager.__singleton
