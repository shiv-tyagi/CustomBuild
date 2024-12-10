import re
import logging
from utils import TaskRunner
import os
from .manager import (
    BuildManager,
    BuildState
)

logger = logging.getLogger(__name__)


class BuildProgressUpdater:
    """
    Class for updating build progress.
    """

    __singleton = None

    def __init__(self):
        """
        Initialises the BuildProgressUpdater instance.
        This uses the BuildManager singleton, make sure to initialise that first.

        Raises:
            RuntimeError: If BuildManager is not initialised or
                          if another instance of BuildProgressUpdater has already
                          been initialised.

        """
        if not BuildManager.get_singleton():
            raise RuntimeError("BuildManager should be initialsed first")

        if BuildProgressUpdater.__singleton:
            raise RuntimeError("BuildProgressUpdater should be a singleton")

        self.__bm = BuildManager.get_singleton()

        # Call self.__update_running_build_progress_all every three seconds.
        # This spins up a new thread.
        tasks = (
            (self.__update_running_build_progress_all, 3),
        )
        self.__runner = TaskRunner(tasks=tasks)
        BuildProgressUpdater.__singleton = self

    def __calc_build_progress_percent(self, build_id: str) -> int:
        """
        Return the percentage of build completion.

        Parameters:
            build_id (str): the unique id for the build.

        Returns:
            int: the calculated build progress percentage.
        
        Raises:
            ValueError: If no build is found for the build id.
        """
        build_info = self.__bm.get_build_info(build_id=build_id)
        logger.debug(f"Calculating progress for build: {build_info}")

        if build_info is None:
            raise ValueError(f"No Build found with id {build_id}")

        if build_info.progress.state in [BuildState.PENDING, BuildState.ERROR]:
            return 0

        if build_info.progress.state == BuildState.SUCCESS:
            return 100

        log_file_path = os.path.join(
            self.__bm.get_outdir(),
            build_id,
            'build.log'
        )
        logger.debug('Opening log file ' + log_file_path)
        with open(log_file_path, encoding='utf-8') as f:
            build_log = f.read()

        compiled_regex = re.compile(r'(\[\D*(\d+)\D*\/\D*(\d+)\D*\])')
        logger.debug(f"Regex: {compiled_regex}")
        all_matches = compiled_regex.findall(build_log)
        logger.debug(f"Matches: {all_matches}")

        if (len(all_matches) < 1):
            return 0

        completed_steps, total_steps = all_matches[-1][1:]
        logger.debug(
            f"Completed steps: {completed_steps}, "
            f"Total Steps: {total_steps}"
        )
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
        """
        Update progress of all running builds.
        """
        for build_id in self.__bm.get_running_build_ids():
            percent = self.__calc_build_progress_percent(build_id=build_id)
            logger.debug(f"New percentage for build id {build_id}: {percent}")
            self.__bm.update_build_progress_percent(
                build_id=build_id,
                percent=percent
            )

    @staticmethod
    def get_singleton() -> "BuildProgressUpdater":
        return BuildProgressUpdater.__singleton
