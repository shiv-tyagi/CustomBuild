# filepath: /home/shiv/dev/CustomBuild/web_new/app/services/builds.py
"""
Builds service for handling build-related business logic.
"""
import base64
import logging
import os
from typing import List, Optional

from app.schemas import (
    BuildRequest,
    BuildSubmitResponse,
    BuildOut,
    BuildProgress,
    RemoteInfo,
)
from app.core.config import setup_external_modules_path

# Setup path before importing external modules
setup_external_modules_path()

# Import external modules
# pylint: disable=wrong-import-position
import build_manager  # noqa: E402

logger = logging.getLogger(__name__)


class BuildsService:
    """Service for managing firmware builds."""

    def __init__(
        self,
        build_manager=None,
        versions_fetcher=None,
        ap_src_metadata_fetcher=None,
        repo=None
    ):
        self.manager = build_manager
        self.versions_fetcher = versions_fetcher
        self.ap_src_metadata_fetcher = ap_src_metadata_fetcher
        self.repo = repo

    @staticmethod
    def parse_version_id(
        version_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Parse composite version_id into remote_name and commit_ref.
        Format: {remote_name}:{base64_encoded_commit_ref}
        Returns: (remote_name, commit_ref) or (None, None) if invalid
        """
        try:
            remote_name, encoded_commit_ref = version_id.split(':', 1)
            commit_ref = base64.urlsafe_b64decode(encoded_commit_ref).decode()
            return remote_name, commit_ref
        except Exception:
            return None, None

    def create_build(
        self,
        build_request: BuildRequest,
        client_ip: str
    ) -> BuildSubmitResponse:
        """
        Create a new build request.

        Args:
            build_request: Build configuration
            client_ip: Client IP address for rate limiting

        Returns:
            Simple response with build_id and URL

        Raises:
            ValueError: If validation fails
        """
        # Parse and validate version_id
        if not build_request.version_id:
            raise ValueError("version_id is required")

        remote_name, commit_ref = self.parse_version_id(
            build_request.version_id
        )
        if not remote_name or not commit_ref:
            raise ValueError("Invalid version_id format")

        # Validate remote
        remote_info = self.versions_fetcher.get_remote_info(remote_name)
        if remote_info is None:
            raise ValueError(f"Remote {remote_name} is not whitelisted")

        # Validate vehicle
        vehicle_name = build_request.vehicle_id
        if not vehicle_name:
            raise ValueError("vehicle_id is required")

        # Validate version for vehicle
        version_info = self.versions_fetcher.get_version_info(
            vehicle_name=vehicle_name,
            remote=remote_name,
            commit_ref=commit_ref
        )
        if version_info is None:
            raise ValueError("Invalid version for vehicle")

        # Validate board
        board_name = build_request.board_id
        if not board_name:
            raise ValueError("board_id is required")

        # Check board exists at this version
        with self.repo.get_checkout_lock():
            boards_at_commit = self.ap_src_metadata_fetcher.get_boards(
                remote=remote_name,
                commit_ref=commit_ref,
                vehicle=vehicle_name,
            )

        if board_name not in boards_at_commit:
            raise ValueError("Invalid board for this version")

        # Get git hash
        git_hash = self.repo.commit_id_for_remote_ref(
            remote=remote_name,
            commit_ref=commit_ref
        )

        # Create build info
        build_info = build_manager.BuildInfo(
            vehicle=vehicle_name,
            remote_info=remote_info,
            git_hash=git_hash,
            board=board_name,
            selected_features=set(build_request.selected_features or [])
        )

        # Submit build
        build_id = self.manager.submit_build(
            build_info=build_info,
            client_ip=client_ip,
        )

        logger.info(f'Build {build_id} submitted successfully')

        # Return simple submission response
        return BuildSubmitResponse(
            build_id=build_id,
            url=f"/api/v1/builds/{build_id}",
            status="submitted"
        )

    def list_builds(
        self,
        vehicle_id: Optional[str] = None,
        board_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[BuildOut]:
        """
        Get list of builds with optional filters.

        Args:
            vehicle_id: Filter by vehicle
            board_id: Filter by board
            state: Filter by build state
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of builds
        """
        all_build_ids = self.manager.get_all_build_ids()
        all_builds = []

        for build_id in all_build_ids:
            build_info = self.manager.get_build_info(build_id)
            if build_info is None:
                continue

            # Apply filters
            if vehicle_id and build_info.vehicle.lower() != vehicle_id.lower():
                continue
            if board_id and build_info.board != board_id:
                continue
            if state and build_info.progress.state.name != state:
                continue

            all_builds.append(
                self._build_info_to_output(build_id, build_info)
            )

        # Sort by creation time (newest first)
        all_builds.sort(key=lambda x: x.time_created, reverse=True)

        # Apply pagination
        return all_builds[offset:offset + limit]

    def get_build(self, build_id: str) -> Optional[BuildOut]:
        """
        Get details of a specific build.

        Args:
            build_id: The unique build identifier

        Returns:
            Build details or None if not found
        """
        if not self.manager.build_exists(build_id):
            return None

        build_info = self.manager.get_build_info(build_id)
        if build_info is None:
            return None

        return self._build_info_to_output(build_id, build_info)

    def get_build_logs(
        self,
        build_id: str,
        tail: Optional[int] = None
    ) -> Optional[str]:
        """
        Get build logs for a specific build.

        Args:
            build_id: The unique build identifier
            tail: Optional number of last lines to return

        Returns:
            Build logs as text or None if not found/available
        """
        if not self.manager.build_exists(build_id):
            return None

        log_path = self.manager.get_build_log_path(build_id)
        if not os.path.exists(log_path):
            return None

        try:
            with open(log_path, 'r') as f:
                if tail:
                    # Read last N lines
                    lines = f.readlines()
                    return ''.join(lines[-tail:])
                else:
                    return f.read()
        except Exception as e:
            logger.error(f"Error reading log file for build {build_id}: {e}")
            return None

    def get_artifact_path(self, build_id: str) -> Optional[str]:
        """
        Get the path to the build artifact.

        Args:
            build_id: The unique build identifier

        Returns:
            Path to artifact or None if not available
        """
        if not self.manager.build_exists(build_id):
            return None

        build_info = self.manager.get_build_info(build_id)
        if build_info is None:
            return None

        # Only return artifact if build was successful
        if build_info.progress.state.name != "SUCCESS":
            return None

        artifact_path = self.manager.get_build_archive_path(build_id)
        if os.path.exists(artifact_path):
            return artifact_path

        return None

    def _build_info_to_output(
        self,
        build_id: str,
        build_info
    ) -> BuildOut:
        """
        Convert BuildInfo object to BuildOut schema.

        Args:
            build_id: The build identifier
            build_info: BuildInfo object from build_manager

        Returns:
            BuildOut schema object
        """
        # Convert build_manager.BuildProgress to schema BuildProgress
        progress = BuildProgress(
            percent=build_info.progress.percent,
            state=build_info.progress.state.name,
            message=None
        )

        # Convert RemoteInfo
        remote_info = RemoteInfo(
            name=build_info.remote_info.name,
            url=build_info.remote_info.url
        )

        # Generate URLs
        artifact_url = None
        log_url = None

        if build_info.progress.state.name == "SUCCESS":
            artifact_url = f"/api/v1/builds/{build_id}/artifact"

        if os.path.exists(self.manager.get_build_log_path(build_id)):
            log_url = f"/api/v1/builds/{build_id}/logs"

        # Get timestamps
        time_started = getattr(build_info, 'time_started', None)
        time_completed = getattr(build_info, 'time_completed', None)

        return BuildOut(
            build_id=build_id,
            vehicle_name=build_info.vehicle,
            board_name=build_info.board,
            git_hash=build_info.git_hash,
            remote_info=remote_info,
            selected_features=list(build_info.selected_features),
            progress=progress,
            time_created=build_info.time_created,
            time_started=time_started,
            time_completed=time_completed,
            artifact_url=artifact_url,
            log_url=log_url
        )


def get_builds_service(request) -> BuildsService:
    """
    Get BuildsService instance with dependencies from app state.

    Args:
        request: FastAPI Request object

    Returns:
        BuildsService instance initialized with app state dependencies
    """
    return BuildsService(
        build_manager=request.app.state.build_manager,
        versions_fetcher=request.app.state.versions_fetcher,
        ap_src_metadata_fetcher=request.app.state.ap_src_metadata_fetcher,
        repo=request.app.state.repo,
    )
