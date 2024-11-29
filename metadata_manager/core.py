import logging
import time
import os
import fnmatch
import ap_git
import json
import jsonschema
import subprocess
import enum
import re
import redis
import pickle
from typing import Callable
from . import exceptions as ex
from threading import Lock
from .utils import TaskRunner

logger = logging.getLogger(__name__)


class APSourceMetadataFetcher:
    """
    Class to fetch metadata like available boards, features etc.
    from the AP source code
    """

    __singleton = None

    def __init__(self, ap_repo_path: str) -> None:
        """
        Initializes the APSourceMetadataFetcher instance
        with a given repository path.

        Parameters:
            ap_repo_path (str): Path to the repository where
                                metadata scripts are located.

        Raises:
            TooManyInstancesError: If an instance of this class already exists,
                                   enforcing a singleton pattern.
        """
        # Enforce singleton pattern by raising an error if
        # an instance already exists.
        if APSourceMetadataFetcher.__singleton:
            raise ex.TooManyInstancesError()

        # Initialize the Git repository object pointing to the source repo.
        self.repo = ap_git.GitRepo(local_path=ap_repo_path)
        APSourceMetadataFetcher.__singleton = self

    def get_boards_at_commit(self, remote: str,
                             commit_ref: str) -> tuple:
        """
        Retrieves a list of boards available for building at a
        specified commit and returns the list and the default board.

        Parameters:
            remote (str): The name of the remote repository.
            commit_ref (str): The commit reference to check out.

        Returns:
            tuple: A tuple containing:
                - boards (list): A list of boards available at the
                                 specified commit.
                - default_board (str): The first board in the sorted list,
                                       designated as the default.
        """
        tstart = time.time()
        import importlib.util
        with self.repo.get_checkout_lock():
            self.repo.checkout_remote_commit_ref(
                remote=remote,
                commit_ref=commit_ref,
                force=True,
                hard_reset=True,
                clean_working_tree=True
            )
            spec = importlib.util.spec_from_file_location(
                name="board_list.py",
                location=os.path.join(
                    self.repo.get_local_path(),
                    'Tools', 'scripts',
                    'board_list.py')
                )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            all_boards = mod.AUTOBUILD_BOARDS
        exclude_patterns = ['fmuv*', 'SITL*']
        boards = []
        for b in all_boards:
            excluded = False
            for p in exclude_patterns:
                if fnmatch.fnmatch(b.lower(), p.lower()):
                    excluded = True
                    break
            if not excluded:
                boards.append(b)
        logger.debug(
            f"Took {(time.time() - tstart)} seconds to get boards"
        )
        boards.sort()
        default_board = boards[0]
        return (boards, default_board)

    def get_build_options_at_commit(self, remote: str,
                                    commit_ref: str) -> list:
        """
        Retrieves a list of build options available at a specified commit.

        Parameters:
            remote (str): The name of the remote repository.
            commit_ref (str): The commit reference to check out.

        Returns:
            list: A list of build options available at the specified commit.
        """
        tstart = time.time()
        import importlib.util
        with self.repo.get_checkout_lock():
            self.repo.checkout_remote_commit_ref(
                remote=remote,
                commit_ref=commit_ref,
                force=True,
                hard_reset=True,
                clean_working_tree=True
            )
            spec = importlib.util.spec_from_file_location(
                name="build_options.py",
                location=os.path.join(
                    self.repo.get_local_path(),
                    'Tools',
                    'scripts',
                    'build_options.py'
                )
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            build_options = mod.BUILD_OPTIONS
        logger.debug(
            f"Took {(time.time() - tstart)} seconds to get build options"
        )
        return build_options

    @staticmethod
    def get_singleton():
        return APSourceMetadataFetcher.__singleton


class VersionInfo:
    """
    Class to wrap version info properties inside a single object
    """
    def __init__(self,
                 remote: str,
                 commit_ref: str,
                 release_type: str,
                 version_number: str,
                 ap_build_artifacts_url) -> None:
        self.remote = remote
        self.commit_ref = commit_ref
        self.release_type = release_type
        self.version_number = version_number
        self.ap_build_artifacts_url = ap_build_artifacts_url


class RemoteInfo:
    """
    Class to wrap remote info properties inside a single object
    """
    def __init__(self,
                 name: str,
                 url: str) -> None:
        self.name = name
        self.url = url


class VersionsFetcher:
    """
    Class to fetch the version-to-build metadata from remotes.json
    and provide methods to view the same
    """

    __singleton = None

    def __init__(self, remotes_json_path: str,
                 post_metadata_reload_callback: Callable[..., object]):
        """
        Initializes the VersionsFetcher instance
        with a given remotes.json path.

        Parameters:
            remotes_json_path (str): Path to the remotes.json file.
            post_metadata_reload_callback (Callable):
                Function to call after reloading remotes.json.
                This is used to process and propagate the updated
                metadata at wherever needed.

        Raises:
            TooManyInstancesError: If an instance of this class already exists,
                                   enforcing a singleton pattern.
        """
        # Enforce singleton pattern by raising an error if
        # an instance already exists.
        if VersionsFetcher.__singleton:
            raise ex.TooManyInstancesError()

        self.__remotes_json_path = remotes_json_path
        self.__access_lock_versions_metadata = Lock()
        self.__versions_metadata = []
        tasks = (
            (self.fetch_ap_releases, 1200),
            (self.fetch_whitelisted_tags, 1200),
        )
        self.__task__runner = TaskRunner(tasks=tasks)
        self.__post_meta_refresh_cb = post_metadata_reload_callback
        VersionsFetcher.__singleton = self

    def get_all_remotes_info(self) -> list[RemoteInfo]:
        """
        Return the list of RemoteInfo objects constructed from the
        information in the remotes.json file

        Returns:
            list: RemoteInfo objects for all remotes mentioned in remotes.json
        """
        return [
            RemoteInfo(
                name=remote.get('name', None),
                url=remote.get('url', None)
            )
            for remote in self.__get_versions_metadata()
        ]

    def get_versions_for_vehicle(self, vehicle_name: str) -> list[VersionInfo]:
        """
        Return the list of dictionaries containing the info about the
        versions listed to be built for a particular vehicle.

        Parameters:
            vehicle_name (str): the vehicle to fetch versions list for

        Returns:
            list: VersionInfo objects for all versions allowed to be
                  built for the said vehicle.

        """
        if vehicle_name is None:
            raise ValueError("Vehicle is a required parameter.")

        versions_list = []
        for remote in self.__get_versions_metadata():
            for vehicle in remote['vehicles']:
                if vehicle['name'] != vehicle_name:
                    continue

                for release in vehicle['releases']:
                    versions_list.append(VersionInfo(
                        remote=remote.get('name', None),
                        commit_ref=release.get('commit_reference', None),
                        release_type=release.get('release_type', None),
                        version_number=release.get('version_number', None),
                        ap_build_artifacts_url=release.get(
                            'ap_build_artifacts_url',
                            None
                        )
                    ))
        return versions_list

    def get_all_vehicles_sorted_uniq(self) -> list[str]:
        """
        Return a sorted list of all vehicles listed in remotes.json structure

        Returns:
            list: Vehicles listed in remotes.json

        """
        vehicles_set = set()
        for remote in self.__get_versions_metadata():
            for vehicle in remote['vehicles']:
                vehicles_set.add(vehicle['name'])
        return sorted(list(vehicles_set))

    def is_version_listed(self, vehicle: str, remote: str,
                          commit_ref: str) -> bool:
        """
        Check if a version with given properties mentioned in remotes.json

        Parameters:
            vehicle (str): vehicle for which version is listed
            remote (str): remote under which the version is listed
            commit_ref(str): commit reference for the version

        Returns:
            bool: True if the said version is mentioned in remotes.json,
                  False otherwise

        """
        if vehicle is None:
            raise ValueError("Vehicle is a required parameter.")

        if remote is None:
            raise ValueError("Remote is a required parameter.")

        if commit_ref is None:
            raise ValueError("Commit reference is a required parameter.")

        return (remote, commit_ref) in [
            (version_info.remote, version_info.commit_ref)
            for version_info in
            self.get_versions_for_vehicle(vehicle_name=vehicle)
        ]

    def get_version_info(self, vehicle: str, remote: str,
                         commit_ref: str) -> VersionInfo:
        """
        Find first version matching the given properties in remotes.json

        Parameters:
            vehicle (str): vehicle for which version is listed
            remote (str): remote under which the version is listed
            commit_ref(str): commit reference for the version

        Returns:
            VersionInfo: Object for the version matching the properties,
                         None if not found

        """
        return next(
            (
                version
                for version in self.get_versions_for_vehicle(
                    vehicle_name=vehicle
                )
                if version.remote == remote and
                version.commit_ref == commit_ref
            ),
            None
        )

    def reload_remotes_json(self) -> None:
        """
        Read remotes.json, validate its structure against the schema
        and cache it in memory
        """
        # load file containing vehicles listed to be built for each
        # remote along with the branches/tags/commits on which the
        # firmware can be built
        remotes_json_schema_path = os.path.join(
            os.path.dirname(__file__),
            'remotes.schema.json'
        )
        with open(self.__remotes_json_path, 'r') as f, \
             open(remotes_json_schema_path, 'r') as s:
            versions_metadata = json.loads(f.read())
            schema = json.loads(s.read())
            # validate schema
            jsonschema.validate(instance=versions_metadata, schema=schema)
            self.__set_versions_metadata(versions_metadata=versions_metadata)

        # Version metadata post-refresh callback
        self.__post_meta_refresh_cb()

    def __set_versions_metadata(self, versions_metadata: list) -> None:
        """
        Set versions metadata property with the one passed as parameter
        This requires to acquire the access lock to avoid overwriting the
        object while it is being read
        """
        if versions_metadata is None:
            raise ValueError("versions_metadata is a required parameter. "
                             "Cannot be None.")

        with self.__access_lock_versions_metadata:
            self.__versions_metadata = versions_metadata

    def __get_versions_metadata(self) -> list:
        """
        Read versions metadata property
        This requires to acquire the access lock to avoid reading the list
        while it is being modified

        Returns:
            list: the versions metadata list
        """
        with self.__access_lock_versions_metadata:
            return self.__versions_metadata

    def fetch_ap_releases(self) -> None:
        """
        Execute the fetch_releases.py script to update remotes.json
        with Ardupilot's official releases
        """
        subprocess.run(
            args=['python', 'fetch_releases.py'],
            cwd=os.path.join(
                os.path.dirname(__file__),
                '..',
                'scripts',
            ),
            shell=False,
            check=True
        )
        self.reload_remotes_json()
        return

    def fetch_whitelisted_tags(self) -> None:
        """
        Execute the fetch_whitelisted_tags.py script to update
        remotes.json with tags from whitelisted repos
        """
        subprocess.run(
            args=['python', 'fetch_whitelisted_tags.py'],
            cwd=os.path.join(
                os.path.dirname(__file__),
                '..',
                'scripts',
            ),
            shell=False,
            check=True
        )
        self.reload_remotes_json()
        return

    @staticmethod
    def get_singleton():
        return VersionsFetcher.__singleton


class BuildState(enum.Enum):
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
                 id: str,
                 vehicle: str,
                 remote: RemoteInfo,
                 git_hash: str,
                 selected_features: list,
                 progress: BuildProgress,
                 outdir: str,
                 time_submitted: float) -> None:
        self.id = id
        self.vehicle = vehicle
        self.remote = remote
        self.git_hash = git_hash
        self.selected_features = selected_features
        self.progress = progress
        self.outdir = outdir
        self.time_submitted = time_submitted


class BuildMetadataManager:
    def __init__(self,
                 redis_host: str = 'localhost',
                 redis_port: str = 6379) -> None:
        # Enforce singleton pattern by raising an error if
        # an instance already exists.
        if BuildMetadataManager.__singleton:
            raise ex.TooManyInstancesError()

        self.__redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.__build_entry_prefix = "build_meta:"
        self.__runner = TaskRunner(
            (self.__update_running_build_progress_all, 3)
        )

    def __del__(self) -> None:
        self.__redis_client.close()

    def key_from_build_id(self, build_id: str):
        return self.__build_entry_prefix + build_id

    def build_id_from_key(self, key: str):
        return key[len(self.__build_entry_prefix):]

    def build_exists(self,
                     build_id: str) -> bool:
        return self.__redis_client.exists(self.key_from_build_id(build_id=build_id))

    def add_build_info(self,
                       build_info: BuildInfo,
                       ttl_sec: int = 86400) -> None:
        if self.build_exists(build_id=build_info.id):
            raise ValueError(f"build with id {build_info.id} already exists")

        self.__redis_client.set(
            self.key_from_build_id(build_info.id),
            pickle.dumps(build_info),
            ex=ttl_sec
        )

    def get_build_info(self,
                       build_id: str) -> BuildInfo:
        key = self.key_from_build_id(build_id=build_id)
        value = self.__redis_client.get(key)
        return pickle.loads(value) if value else None

    def __update_build_progress(self,
                                build_id: str,
                                progress: BuildProgress) -> None:
        build_info = self.get_build_info(build_id=build_id)
        build_info.progress = progress
        self.__redis_client.set(
            self.key_from_build_id(build_id=build_info.id),
            pickle.dumps(build_info),
            keepttl=True
        )

    def __update_build_progress_percent(self,
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

    def __get_all_build_ids(self) -> list:
        keys = self.__redis_client.keys(f"{self.__build_entry_prefix}*")
        return [
            self.build_id_from_key(key.decode('utf-8'))
            for key in keys
        ]

    def __get_running_build_ids(self) -> list:
        return [
            build_id for build_id in self.__get_all_build_ids()
            if self.get_build_info(build_id=build_id).progress.state == BuildState.RUNNING
        ]

    def __calc_build_progress_percent(self, build_id: str) -> int:
        build_info = self.get_build_info(build_id=build_id)

        if build_info is None:
            raise Exception(f"No Build found with id {build_id}")

        if build_info.progress.state in [BuildState.PENDING, BuildState.ERROR]:
            return 0

        if build_info.progress.state == BuildState.SUCCESS:
            return 100

        log_file_path = os.path.join(build_info.outdir, 'build.log')
        logger.debug('Opening ' + log_file_path)
        with open(log_file_path, encoding='utf-8') as f:
            build_log = f.read()

        compiled_regex = re.compile(r'(\[\D*(\d+)\D*\/\D*(\d+)\D*\])')
        all_matches = compiled_regex.findall(build_log)

        if (len(all_matches) < 1):
            return 0

        completed_steps, total_steps = all_matches[-1][1:]
        if (int(total_steps) < 20):
            # these steps are just little compilation and linking
            # that happens at initialisation, these do not contribute 
            # significant percentage to overall build progress
            return 1

        if (int(total_steps) < 200):
            # these steps are for building the OS
            # we give this phase 4% weight in the whole build progress
            return (int(completed_steps) * 4 // int(total_steps)) + 1

        # these steps are the major part of the build process
        # we give 95% of weight to these
        return (int(completed_steps) * 95 // int(total_steps)) + 5

    def __update_running_build_progress_all(self):
        for build_id in self.__get_running_build_ids():
            percent = self.__calc_build_progress_percent(build_id=build_id)
            self.__update_build_progress_percent(
                build_id=build_id,
                percent=percent
            )

    @staticmethod
    def get_singleton():
        return BuildMetadataManager.__singleton


class RateLimiter:
    def __init__(self):
        return
    

