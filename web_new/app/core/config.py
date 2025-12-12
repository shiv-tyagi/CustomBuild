"""
Application configuration and settings.
"""
import os
import sys
from pathlib import Path
from functools import lru_cache


class Settings:
    """Application settings."""

    def __init__(self):
        # Application
        self.app_name: str = "CustomBuild API"
        self.app_version: str = "1.0.0"
        self.debug: bool = False

        # Paths
        self.base_dir: str = os.getenv(
            "CBS_BASEDIR",
            default=str(Path(__file__).parent.parent.parent.parent / "base")
        )

        # Redis
        self.redis_host: str = os.getenv(
            'CBS_REDIS_HOST',
            default='localhost'
        )
        self.redis_port: str = os.getenv(
            'CBS_REDIS_PORT',
            default='6379'
        )

        # Logging
        self.log_level: str = os.getenv('CBS_LOG_LEVEL', default='INFO')

        # ArduPilot Git Repository
        self.ap_git_url: str = "https://github.com/ardupilot/ardupilot.git"

    @property
    def source_dir(self) -> str:
        """ArduPilot source directory."""
        return os.path.join(self.base_dir, 'ardupilot')

    @property
    def artifacts_dir(self) -> str:
        """Build artifacts directory."""
        return os.path.join(self.base_dir, 'artifacts')

    @property
    def outdir_parent(self) -> str:
        """Build output directory (same as artifacts_dir)."""
        return self.artifacts_dir

    @property
    def workdir_parent(self) -> str:
        """Work directory parent."""
        return os.path.join(self.base_dir, 'workdir')

    @property
    def remotes_json_path(self) -> str:
        """Path to remotes.json configuration."""
        return os.path.join(self.base_dir, 'configs', 'remotes.json')


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def setup_external_modules_path():
    """
    Add parent directory to sys.path to access modules outside web_new.
    This allows importing ap_git, metadata_manager, build_manager, etc.
    """
    # Get the parent directory of web_new (i.e., CustomBuild root)
    project_root = Path(__file__).parent.parent.parent.parent
    project_root_str = str(project_root.resolve())

    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


# Setup path on import
setup_external_modules_path()
