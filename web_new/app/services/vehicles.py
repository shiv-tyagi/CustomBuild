"""
Vehicles service for handling vehicle-related business logic.
"""
import base64
import logging
from typing import List, Optional
import requests
from fastapi import Request

from app.schemas import (
    VehicleBase,
    VersionOut,
    BoardOut,
    FeatureOut,
    CategoryBase,
    DefaultsOut,
)
from app.core.config import setup_external_modules_path

# Setup path before importing external modules
setup_external_modules_path()

logger = logging.getLogger(__name__)


class VehiclesService:
    """Service for managing vehicles, versions, boards, and features."""

    def __init__(self, vehicle_manager=None,
                 versions_fetcher=None,
                 ap_src_metadata_fetcher=None,
                 repo=None):
        self.vehicles_manager = vehicle_manager
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

    @staticmethod
    def create_version_id(remote_name: str, commit_ref: str) -> str:
        """
        Create composite version_id from remote_name and commit_ref.
        Format: {remote_name}:{base64_encoded_commit_ref}
        """
        encoded_commit_ref = base64.urlsafe_b64encode(
            commit_ref.encode()
        ).decode()
        return f"{remote_name}:{encoded_commit_ref}"

    def get_all_vehicles(self) -> List[VehicleBase]:
        """Get list of all available vehicles."""
        logger.info('Fetching all vehicles')
        vehicle_names = self.vehicles_manager.get_all_vehicle_names_sorted()
        logger.info(f'Found vehicles: {vehicle_names}')
        return [
            VehicleBase(id=name.lower(), name=name)
            for name in vehicle_names
        ]

    def get_vehicle(self, vehicle_id: str) -> Optional[VehicleBase]:
        """Get a specific vehicle by ID."""
        # Convert vehicle_id (lowercase) to proper case vehicle name
        vehicle_names = self.vehicles_manager.get_all_vehicle_names_sorted()

        for name in vehicle_names:
            if name.lower() == vehicle_id.lower():
                return VehicleBase(id=name.lower(), name=name)

        return None

    def get_versions(
        self,
        vehicle_id: str,
        type_filter: Optional[str] = None
    ) -> List[VersionOut]:
        """Get all versions available for a specific vehicle."""
        # Convert vehicle_id to proper vehicle name
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return []

        vehicle_name = vehicle.name
        versions = []

        for version_info in self.versions_fetcher.get_versions_for_vehicle(
            vehicle_name=vehicle_name
        ):
            # Apply type filter if provided
            if type_filter and version_info.release_type != type_filter:
                continue

            if version_info.release_type == "latest":
                title = f"Latest ({version_info.remote})"
            else:
                rel_type = version_info.release_type
                ver_num = version_info.version_number
                remote = version_info.remote
                title = f"{rel_type} {ver_num} ({remote})"

            version_id = self.create_version_id(
                version_info.remote,
                version_info.commit_ref
            )

            versions.append(VersionOut(
                id=version_id,
                name=title,
                type=version_info.release_type,
                remote_name=version_info.remote,
                commit_ref=version_info.commit_ref,
                vehicle_name=vehicle_name
            ))

        # Sort by name
        return sorted(versions, key=lambda x: x.name)

    def get_version(
        self,
        vehicle_id: str,
        version_id: str
    ) -> Optional[VersionOut]:
        """Get details of a specific version for a vehicle."""
        versions = self.get_versions(vehicle_id)
        for version in versions:
            if version.id == version_id:
                return version
        return None

    def get_boards(
        self,
        vehicle_id: str,
        version_id: str
    ) -> List[BoardOut]:
        """Get all boards available for a specific vehicle version."""
        # Parse version_id
        remote_name, commit_ref = self.parse_version_id(version_id)
        if not remote_name or not commit_ref:
            return []

        # Get vehicle name
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return []

        vehicle_name = vehicle.name

        # Check if version is listed
        is_listed = self.versions_fetcher.is_version_listed(
            vehicle_name=vehicle_name,
            remote=remote_name,
            commit_ref=commit_ref
        )
        if not is_listed:
            return []

        logger.info(
            f'Board list requested for {vehicle_name} '
            f'{remote_name} {commit_ref}'
        )

        # Get boards list
        with self.repo.get_checkout_lock():
            boards = self.ap_src_metadata_fetcher.get_boards(
                remote=remote_name,
                commit_ref=commit_ref,
                vehicle=vehicle_name,
            )

        return [
            BoardOut(
                id=board,
                name=board,
                vehicle_name=vehicle_name,
                version_id=version_id
            )
            for board in boards
        ]

    def get_board(
        self,
        vehicle_id: str,
        version_id: str,
        board_id: str
    ) -> Optional[BoardOut]:
        """Get details of a specific board for a vehicle version."""
        boards = self.get_boards(vehicle_id, version_id)
        for board in boards:
            if board.id == board_id:
                return board
        return None

    def get_features(
        self,
        vehicle_id: str,
        version_id: str,
        category_id: Optional[str] = None
    ) -> List[FeatureOut]:
        """Get all features available for a specific vehicle version."""
        # Parse version_id
        remote_name, commit_ref = self.parse_version_id(version_id)
        if not remote_name or not commit_ref:
            return []

        # Get vehicle name
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return []

        vehicle_name = vehicle.name

        # Check if version is listed
        is_listed = self.versions_fetcher.is_version_listed(
            vehicle_name=vehicle_name,
            remote=remote_name,
            commit_ref=commit_ref
        )
        if not is_listed:
            return []

        logger.info(
            f'Features requested for {vehicle_name} {remote_name} {commit_ref}'
        )

        # Get build options
        with self.repo.get_checkout_lock():
            options = self.ap_src_metadata_fetcher.get_build_options_at_commit(
                remote=remote_name,
                commit_ref=commit_ref
            )

        features = []
        for option in options:
            # Apply category filter if provided
            if category_id and option.category != category_id:
                continue

            features.append(FeatureOut(
                id=option.define,
                name=option.label,
                category=CategoryBase(
                    id=option.category,
                    name=option.category,
                    description=None
                ),
                defaultEnabled=option.default,
                description=option.description,
                vehicle_name=vehicle_name,
                version_id=version_id
            ))

        # Sort by name
        return sorted(features, key=lambda x: x.name.lower())

    def get_feature(
        self,
        vehicle_id: str,
        version_id: str,
        feature_id: str
    ) -> Optional[FeatureOut]:
        """Get details of a specific feature for a vehicle version."""
        features = self.get_features(vehicle_id, version_id)
        for feature in features:
            if feature.id == feature_id:
                return feature
        return None

    def get_defaults(
        self,
        vehicle_id: str,
        version_id: str,
        board_id: str
    ) -> List[DefaultsOut]:
        """Get default feature settings for a specific board."""
        # Parse version_id
        remote_name, commit_ref = self.parse_version_id(version_id)
        if not remote_name or not commit_ref:
            return []

        # Get vehicle name
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return []

        vehicle_name = vehicle.name
        board_name = board_id

        # Heli is built on copter
        if vehicle_name == "Heli":
            vehicle_name = "Copter"
            board_name += "-heli"

        # Get version info
        version_info = self.versions_fetcher.get_version_info(
            vehicle_name=vehicle_name,
            remote=remote_name,
            commit_ref=commit_ref
        )

        if version_info is None:
            return []

        artifacts_dir = version_info.ap_build_artifacts_url
        if artifacts_dir is None:
            return []

        # Fetch features.txt from ArduPilot server
        url_to_features_txt = f"{artifacts_dir}/{board_name}/features.txt"

        try:
            response = requests.get(url_to_features_txt, timeout=30)
            response.raise_for_status()

            # Split response by newline to get list of defines
            feature_ids = response.text.strip().split('\n')

            # Filter out empty lines
            feature_ids = [f.strip() for f in feature_ids if f.strip()]

            return [
                DefaultsOut(
                    feature_id=feature_id,
                    enabled=True,
                    vehicle_name=vehicle_name,
                    version_id=version_id,
                    board_id=board_id
                )
                for feature_id in feature_ids
            ]
        except requests.RequestException as e:
            logger.error(
                f"Failed to fetch defaults from {url_to_features_txt}: {e}"
            )
            return []

    def get_default(
        self,
        vehicle_id: str,
        version_id: str,
        board_id: str,
        feature_id: str
    ) -> Optional[DefaultsOut]:
        """Get default setting for a specific feature on a board."""
        defaults = self.get_defaults(vehicle_id, version_id, board_id)
        for default in defaults:
            if default.feature_id == feature_id:
                return default
        return None


def get_vehicles_service(request: Request) -> VehiclesService:
    """
    Get VehiclesService instance with dependencies from app state.

    Args:
        request: FastAPI Request object

    Returns:
        VehiclesService instance initialized with app state dependencies
    """
    return VehiclesService(
        vehicle_manager=request.app.state.vehicles_manager,
        versions_fetcher=request.app.state.versions_fetcher,
        ap_src_metadata_fetcher=request.app.state.ap_src_metadata_fetcher,
        repo=request.app.state.repo,
    )
