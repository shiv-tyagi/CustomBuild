import ap_git
from build_manager import (
    BuildManager as bm,
    BuildState
)
import subprocess
import os
import logging
from metadata_manager import (
    APSourceMetadataFetcher as apfetch,
    RemoteInfo,
)

logger = logging.getLogger(__name__)


class Builder:
    """
    Processes build requests, perform builds and ship build artifacts
    to the destination directory shared by BuildManager.
    """

    def __init__(self, appdir: str, workdir: str) -> None:
        """
        Initialises the Builder class.

        Parameters:
            appdir (str): Directory where compiler binaries are stored.
            workdir (str): Parent directory used for building.

        Raises:
            RuntimeError: If BuildManager or APSourceMetadataFetcher is not
            initialised.
        """
        if bm.get_singleton() is None:
            raise RuntimeError(
                "BuildManager should be initialized first."
            )
        if apfetch.get_singleton() is None:
            raise RuntimeError(
                "APSourceMetadataFetcher should be initialised first."
            )

        self.__workdir_parent = workdir
        self.__appdir = appdir
        self.__master_repo = ap_git.GitRepo.clone(
            source="https://github.com/ardupilot/ardupilot.git",
            dest=self.__workdir_parent,
            recurse_submodules=True,
        )

    def __generate_extrahwdef(self, build_id: str) -> None:
        """
        Generates the extra hardware definition file (`extra_hwdef.dat`) for
        the build.

        Parameters:
            build_id (str): Unique identifier for the build.

        Raises:
            RuntimeError: If the parent directory for putting `extra_hwdef.dat`
            does not exist.
        """
        path = self.__get_path_to_extra_hwdef(build_id)
        if not os.path.exists(os.path.dirname(path)):
            raise RuntimeError(
                f"Create parent directory '{os.path.dirname(path)}' "
                "before writing extra_hwdef.dat"
            )

        build_info = bm.get_singleton().get_build_info(build_id)
        selected_features = build_info.selected_features
        all_defines = apfetch.get_singleton().get_defines_at_commit(
            remote=build_info.remote,
            commit_ref=build_info.git_hash,
        )
        enabled_defines = selected_features.intersection(all_defines)
        disabled_defines = all_defines.difference(enabled_defines)

        with open(self.__get_path_to_extra_hwdef(build_id), "w") as f:
            # Undefine all defines at the beginning
            for define in all_defines:
                f.write(f"undef {define}\n")
            # Enable selected defines
            for define in enabled_defines:
                f.write(f"define {define} 1\n")
            # Disable the remaining defines
            for define in disabled_defines:
                f.write(f"define {define} 0\n")

    def __ensure_remote_added(self, remote: RemoteInfo) -> None:
        """
        Ensures that the remote repository is correctly added to the
        master repository.

        Parameters:
            remote (RemoteInfo): Information about the remote repository.
        """
        try:
            self.__master_repo.remote_add(remote=remote.name, url=remote.url)
        except ap_git.DuplicateRemoteError:
            # Update the URL if the remote already exists
            self.__master_repo.remote_set_url(
                remote=remote.name,
                url=remote.url,
            )

    def __provision_build_source(self, build_id: str) -> None:
        """
        Provisions the source code for a specific build.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        build_info = bm.get_singleton().get_build_info(build_id)
        self.__ensure_remote_added(build_info.remote)

        # Clone Git repository for the specific build
        ap_git.GitRepo.shallow_clone_at_commit_from_local(
            source=self.__master_repo.get_local_path(),
            remote=build_info.remote,
            commit_ref=build_info.git_hash,
            dest=self.__get_path_to_build_src(build_id),
        )

    def __create_build_artifacts_dir(self, build_id: str) -> None:
        """
        Creates the output directory to store build artifacts.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        path = bm.get_build_artifacts_dir_path(build_id)
        os.mkdir(path)

    def __create_build_workdir(self, build_id: str) -> None:
        """
        Creates the working directory for the build.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        path = self.__get_path_to_build_dir(build_id)
        os.mkdir(path)

    def __generate_zip(self, build_id: str) -> None:
        """
        Placeholder for generating the zipped build artifact.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        pass

    def __deliver_zip(self, build_id: str) -> None:
        """
        Placeholder for delivering the zipped build artifact.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        pass

    def __claim_build(self, build_id: str) -> None:
        """
        Claim the build and inform build manager.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        bm.get_singleton().update_build_progress_state(
            build_id=build_id,
            new_state=BuildState.RUNNING,
        )

    def __build_already_claimed(self, build_id: str) -> None:
        """
        Returns True if the build has already been claimed by another
        builder.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        build_info = bm.get_singleton().get_build_info(build_id)
        return build_info.progress.state != BuildState.PENDING

    def __process_build(self, build_id: str) -> None:
        """
        Processes a new build by preparing source code and extra_hwdef file
        and running the build finally.

        Parameters:
            build_id (str): Unique identifier for the build.
        """
        if self.__build_already_claimed(build_id):
            logger.error("Build {build_id} has already been claimed.")
            return

        self.__claim_build(build_id)
        self.__create_build_workdir(build_id)
        self.__provision_build_source(build_id)
        self.__generate_extrahwdef(build_id)
        self.__create_build_artifacts_dir(build_id)
        self.__build(build_id)

    def __get_path_to_build_dir(self, build_id: str) -> str:
        """
        Returns the path to the temporary workspace for a build.
        This directory contains the source code and extra_hwdef.dat file.

        Parameters:
            build_id (str): Unique identifier for the build.

        Returns:
            str: Path to the build directory.
        """
        return os.path.join(self.__workdir_parent, build_id)

    def __get_path_to_extra_hwdef(self, build_id: str) -> str:
        """
        Returns the path to the extra_hwdef definition file for a build.

        Parameters:
            build_id (str): Unique identifier for the build.

        Returns:
            str: Path to the extra hardware definition file.
        """
        return os.path.join(
            self.__get_path_to_build_dir(build_id),
            "extra_hwdef.dat",
        )

    def __get_path_to_build_src(self, build_id: str) -> str:
        """
        Returns the path to the source code for a build.

        Parameters:
            build_id (str): Unique identifier for the build.

        Returns:
            str: Path to the build source directory.
        """
        return os.path.join(
            self.__get_path_to_build_dir(build_id),
            "build_src"
        )

    def __build(self, build_id: str) -> None:
        """
        Executes the actual build process for a build.
        This should be called after preparing build source code and
        extra_hwdef file.

        Parameters:
            build_id (str): Unique identifier for the build.

        Raises:
            RuntimeError: If source directory or extra hardware definition
            file does not exist.
        """
        if not os.path.exists(self.__get_path_to_build_dir(build_id)):
            raise RuntimeError("Cannot build without source.")
        if not os.path.exists(self.__get_path_to_build_src(build_id)):
            raise RuntimeError("Cannot build without source code.")
        if not os.path.exists(self.__get_path_to_extra_hwdef(build_id)):
            raise RuntimeError("Cannot build without extra-hwdef.dat file.")

        build_info = bm.get_build_info(build_id)
        source_repo = ap_git.GitRepo(self.__get_path_to_build_src(build_id))

        # Checkout the specific commit and ensure submodules are updated
        source_repo.checkout_remote_commit_ref(
            remote=build_info.remote.name,
            commit_ref=build_info.git_hash,
            force=True,
            hard_reset=True,
            clean_working_tree=True,
        )
        source_repo.submodule_update(init=True, recursive=True, force=True)

        logpath = bm.get_build_log_path(build_id)
        with open(logpath, "a") as log:
            # Log initial configuration
            log.write(
                "Setting vehicle to: "
                f"{build_info.vehicle.capitalize()}\n"
            )
            log.flush()

            # Configure environment variables for the build
            env = os.environ.copy()
            bindir1 = os.path.abspath(
                os.path.join(self.__appdir, "..", "bin")
            )
            bindir2 = os.path.abspath(os.path.join(
                self.__appdir, "..", "gcc", "bin")
            )
            cachedir = os.path.abspath(
                os.path.join(self.__appdir, "..", "cache")
            )
            env["PATH"] = bindir1 + ":" + bindir2 + ":" + env["PATH"]
            env["CCACHE_DIR"] = cachedir

            # Run the build steps
            logger.info("Running waf configure")
            log.write("Running waf configure\n")
            log.flush()
            subprocess.run(
                [
                    "python3",
                    "./waf",
                    "configure",
                    "--board",
                    build_info.board,
                    "--out",
                    self.__get_path_to_build_dir(build_id),
                    "--extra-hwdef",
                    self.__get_path_to_extra_hwdef(build_id),
                ],
                cwd=self.__get_path_to_build_src(build_id),
                env=env,
                stdout=log,
                stderr=log,
                shell=False,
            )

            logger.info("Running clean")
            log.write("Running clean\n")
            log.flush()
            subprocess.run(
                ["python3", "./waf", "clean"],
                cwd=self.__get_path_to_build_src(build_id),
                env=env,
                stdout=log,
                stderr=log,
                shell=False,
            )

            logger.info("Running build")
            log.write("Running build\n")
            log.flush()
            subprocess.run(
                ["python3", "./waf", build_info.vehicle],
                cwd=self.__get_path_to_build_src(build_id),
                env=env,
                stdout=log,
                stderr=log,
                shell=False,
            )
            log.write("done build\n")
            log.flush()

    def run(self) -> None:
        """
        Continuously processes builds in the queue until termination.
        """
        while True:
            build_to_process = bm.get_singleton().get_next_build_id()
            self.__process_build(build_id=build_to_process)
