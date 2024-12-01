import re
import logging
from utils import TaskRunner
from .manager import (
    BuildManager as bm,
    BuildState
)

logger = logging.getLogger(__name__)


class BuildProgressUpdater:
    """
    Class for updating the progress of ongoing builds.

    This class ensures that the progress of all running builds
    is updated periodically. It operates in a singleton pattern
    to ensure only one instance manages the updates.
    """

    __singleton = None

    def __init__(self):
        """
        Initialises the BuildProgressUpdater instance.

        This uses the BuildManager singleton, so ensure that BuildManager is
        initialised before creating a BuildProgressUpdater instance.

        Raises:
            RuntimeError: If BuildManager is not initialized or
            if another instance of BuildProgressUpdater has already
            been initialised.
        """
        if not bm.get_singleton():
            raise RuntimeError("BuildManager should be initialised first")

        if BuildProgressUpdater.__singleton:
            raise RuntimeError("BuildProgressUpdater must be a singleton.")

        # Set up a periodic task to update build progress every 3 seconds
        # TaskRunner will handle scheduling and running the task.
        tasks = (
            (self.__update_running_build_progress_all, 3),
        )
        self.__runner = TaskRunner(tasks=tasks)
        BuildProgressUpdater.__singleton = self

    def __calc_build_progress_percent(self, build_id: str) -> int:
        """
        Calculate the progress percentage of a build.

        This method analyses the build log to determine the current completion
        status by parsing the build steps from the log file.

        Parameters:
            build_id (str): The unique ID of the build for which progress is
            calculated.

        Returns:
            int: The calculated build progress percentage (0 to 100).

        Raises:
            ValueError: If no build information is found for the provided
            build ID.
        """
        build_info = bm.get_singleton().get_build_info(build_id=build_id)
        logger.debug(f"Calculating progress for build: {build_info}")

        if build_info is None:
            raise ValueError(f"No build found with ID {build_id}")

        # Early exit if the build is either pending or has failed
        if build_info.progress.state in [BuildState.PENDING, BuildState.ERROR]:
            return 0

        if build_info.progress.state == BuildState.SUCCESS:
            return 100

        # Construct path to the build's log file
        log_file_path = bm.get_singleton().get_build_log_path(build_id)
        logger.debug(f"Opening log file: {log_file_path}")

        # Read the log content
        try:
            with open(log_file_path, encoding='utf-8') as f:
                build_log = f.read()
        except FileNotFoundError:
            logger.error(f"Log file not found for build ID: {build_id}")
            return 0

        # Regular expression to extract the build progress steps
        compiled_regex = re.compile(r'(\[\D*(\d+)\D*\/\D*(\d+)\D*\])')
        logger.debug(f"Regex pattern: {compiled_regex}")
        all_matches = compiled_regex.findall(build_log)
        logger.debug(f"Log matches: {all_matches}")

        # If no matches are found, return a default progress value of 0
        if len(all_matches) < 1:
            return 0

        completed_steps, total_steps = all_matches[-1][1:]
        logger.debug(
            f"Completed steps: {completed_steps},"
            f"Total steps: {total_steps}"
        )

        # Handle initial compilation/linking steps (minor weight)
        if int(total_steps) < 20:
            return 1

        # Handle building the OS phase (4% weight)
        if int(total_steps) < 200:
            return (int(completed_steps) * 4 // int(total_steps)) + 1

        # Major build phase (95% weight)
        return (int(completed_steps) * 95 // int(total_steps)) + 5

    def __update_running_build_progress_all(self):
        """
        Update progress for all running builds.

        This method will iterate through all running builds, calculate their
        progress, and update the build manager with the latest progress
        percentage.
        """
        for build_id in bm.get_singleton().get_running_build_ids():
            percent = self.__calc_build_progress_percent(build_id=build_id)
            logger.debug(f"New progress for build ID {build_id}: {percent}%")
            bm.get_singleton().update_build_progress_percent(
                build_id=build_id,
                percent=percent
            )

    @staticmethod
    def get_singleton() -> "BuildProgressUpdater":
        """
        Get the singleton instance of BuildProgressUpdater.

        Returns:
            BuildProgressUpdater: The singleton instance of this class.
        """
        return BuildProgressUpdater.__singleton
