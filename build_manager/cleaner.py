import os
from utils import TaskRunner
from .manager import BuildManager
import logging

logger = logging.getLogger(__name__)


class BuildArtifactsCleaner:
    """
    Class to clean stale build artifacts 
    """

    __singleton = None

    def __init__(self) -> None:
        """
        Initializes the BuildArtifactsCleaner instance.
        This uses the BuildManager singleton, make sure to initialise that first.

        Raises:
            RuntimeError: If BuildManager is not initialised or
                          if another instance of BuildArtifactsCleaner has already
                          been initialised.
        """

        if BuildManager.get_singleton() is None:
            raise RuntimeError("BuildManager should be initialsed first")

        if BuildArtifactsCleaner.__singleton:
            raise RuntimeError("BuildArtifactsCleaner must be a singleton")

        self.__bm = BuildManager.get_singleton()

        # Call the self.__run method every 60 seconds
        # This spins up a new thread
        tasks = (
            (self.__run, 60),
        )
        self.__runner = TaskRunner(tasks=tasks)
        BuildArtifactsCleaner.__singleton = self

    def __stale_artifacts_path_list(self) -> list:
        """
        Return a list of paths for each stale build artifacts.

        Returns:
            list: A list of paths.
        """
        dir_to_scan = self.__bm.get_outdir()
        logger.debug(f"Directory to scan: {dir_to_scan}")
        all_build_ids = self.__bm.get_all_build_ids()
        logger.debug(f"All build ids: {all_build_ids}")
        files_to_keep = [
            self.__bm.get_artifacts_fileaname_for_build(build_id=build_id)
            for build_id in all_build_ids
        ]
        logger.debug(f"Keeping files {files_to_keep}")

        stale_artifacts = [
            os.path.join(dir_to_scan, f)
            for f in os.listdir(dir_to_scan)
            if f not in files_to_keep
        ]
        logger.debug(f"Stale artifacts {stale_artifacts}")

        return stale_artifacts

    def __run(self) -> None:
        """
        Delete the stale build artifacts
        """
        for f in self.__stale_artifacts_path_list():
            logger.info(f"Removing artifacts at {f}")
            os.remove(f)
        return

    @staticmethod
    def get_singleton() -> "BuildArtifactsCleaner":
        return BuildArtifactsCleaner.__singleton
