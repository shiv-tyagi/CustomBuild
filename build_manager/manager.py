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
    """
    Class to manage build lifecycle including submission,
    announcements, updates, and retrieval of build-related details.
    """

    __singleton = None

    def __init__(self,
                 outdir: str,
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 redis_announce_channel: str = 'builds-channel') -> None:
        """
        Initialise the BuildManager instance.

        Parameters:
            outdir (str): Path to directory for storing build artifacts.
            redis_host (str): Hostname for redis instance for storing build metadata.
            redis_port (str): Port for redis instance for storing build metadata.
            redis_announce_channel (str): Redis PUB/SUB channel to use for build announcements.
        
        Raises:
            RuntimeError: If an instance of this class already exists,
            enforcing a singleton pattern.
        """
        # Enforce singleton pattern by raising an error if
        # an instance already exists.
        if BuildManager.__singleton:
            raise RuntimeError("BuildManager must be a singleton")

        # Explicitly mentioning to not decode responses as we are using
        # pickle to do that for us
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

        # Initialise an IP based rate limiter
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
        """
        Gracefully close redis connection on object deletion.
        """
        if self.__redis_client:
            logger.debug("Redis connection closed")
            self.__redis_client.close()

    def __key_from_build_id(self, build_id: str) -> str:
        """
        Return redis key which stores the build information for
        given build id.

        Parameters:
            build_id (str): The unique id for the build.
        
        Returns:
            str: The key in redis datastore containing the build information.
        """
        return self.__build_entry_prefix + build_id

    def __build_id_from_key(self, key: str) -> str:
        """
        Return build id for the redis key used to store build information
        in redis datastore.

        Parameters:
            key (str): The key used to store build information in redis db.

        Returns:
            str: The build id for the given key.
        """
        return key[len(self.__build_entry_prefix):]

    def get_outdir(self) -> str:
        """
        Return the directory storing the build artifacts.

        Returns:
            str: Path to the output directory containing the build artifacts.
        """
        return self.__outdir

    def __generate_build_id(self, build_info: BuildInfo) -> str:
        """
        Generate the build id from a given build information.
        We hash the build information and the time to get this token.

        Parameters:
            build_info (BuildInfo): The build information object.

        Returns:
            str: The build id of length 64 characters for the given 
            build information.
        """
        token = hashlib.sha256(
            f"{build_info}-{time.time_ns()}".encode()
        ).hexdigest()
        return token

    def submit_build(self,
                     build_info: BuildInfo,
                     client_ip: str) -> str:
        """
        Accept build submissions and return the build id if the build
        request is accepted.

        Parameters:
            build_info (BuildInfo): The build information
            client_ip (str): The client IP submitting the build request.

        Returns:
            str: The build id for the given build
        """
        self.__ip_rate_limiter.count(client_ip)
        build_id = self.__generate_build_id(build_info)
        self.__add_build_info(build_id=build_id, build_info=build_info)
        self.__announce_build(build_id=build_id)
        return build_id

    def __announce_build(self,
                         build_id: str) -> None:
        """
        Announce the build on the PUB/SUB channel.
        """
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

    def __update_build_info(self,
                            build_id: str,
                            build_info:  BuildInfo) -> None:
        key = self.__key_from_build_id(build_id=build_id)
        logger.debug(
            "Updating build info, "
            f"Redis key: {key}, "
            f"Build Info: {build_info}, "
            f"TTL: Keeping Same"
        )
        self.__redis_client.set(
            name=self.__key_from_build_id(build_id=build_id),
            value=pickle.dumps(build_info),
            keepttl=True
        )

    def update_build_progress_percent(self,
                                      build_id: str,
                                      percent: int) -> None:
        build_info = self.get_build_info(build_id=build_id)

        if build_info is None:
            raise ValueError(f"Build with id {build_id} not found.")

        build_info.progress.percent = percent
        self.__update_build_info(
            build_id=build_id,
            build_info=build_info
        )

    def update_build_progress_state(self,
                                    build_id: str,
                                    new_state: BuildState) -> None:
        build_info = self.get_build_info(build_id=build_id)

        if build_info is None:
            raise ValueError(f"Build with id {build_id} not found.")

        build_info.progress.state = new_state
        self.__update_build_info(
            build_id=build_id,
            build_info=build_info
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
