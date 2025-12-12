from typing import List, Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field


# --- Remote Information ---
class RemoteInfo(BaseModel):
    """Git remote repository information."""
    name: str = Field(..., description="Remote name (e.g., 'ardupilot')")
    url: str = Field(..., description="Git repository URL")


# --- Build Progress ---
class BuildProgress(BaseModel):
    """Build progress and status information."""
    percent: int = Field(
        ..., ge=0, le=100, description="Build completion percentage"
    )
    state: Literal[
        "PENDING", "RUNNING", "SUCCESS", "FAILURE", "CANCELLED"
    ] = Field(..., description="Current build state")
    message: Optional[str] = Field(
        None, description="Optional status message or error details"
    )


# --- Build Request ---
class BuildRequest(BaseModel):
    """Schema for creating a new build request."""
    vehicle_id: str = Field(
        ..., description="Vehicle ID to build for"
    )
    board_id: str = Field(
        ..., description="Board ID to build for"
    )
    version_id: Optional[str] = Field(
        None, description="Version ID for build source code"
    )
    selected_features: List[str] = Field(
        default_factory=list,
        description="Feature IDs to enable for this build"
    )


# --- Build Submit Response ---
class BuildSubmitResponse(BaseModel):
    """Response schema for build submission."""
    build_id: str = Field(..., description="Unique build identifier")
    url: str = Field(..., description="URL to get build details")
    status: Literal["submitted"] = Field(
        ..., description="Build submission status"
    )


# --- Build Output ---
class BuildOut(BaseModel):
    """Complete build information output schema."""
    build_id: str = Field(..., description="Unique build identifier")
    vehicle_name: str = Field(..., description="Target vehicle")
    board_name: str = Field(..., description="Target board")
    git_hash: str = Field(..., description="Git commit hash used for build")
    remote_info: RemoteInfo = Field(
        ..., description="Source repository information"
    )
    selected_features: List[str] = Field(
        default_factory=list,
        description="Enabled feature flags for this build"
    )
    progress: BuildProgress = Field(
        ..., description="Current build status and progress"
    )
    time_created: float = Field(
        ..., description="Unix timestamp when build was created"
    )
    time_started: Optional[float] = Field(
        None, description="Unix timestamp when build started"
    )
    time_completed: Optional[float] = Field(
        None, description="Unix timestamp when build completed"
    )
    artifact_url: Optional[str] = Field(
        None, description="Download URL for completed build artifact"
    )
    log_url: Optional[str] = Field(
        None, description="URL to view build logs"
    )

    @property
    def created_datetime(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.time_created)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate build duration in seconds if completed."""
        if self.time_started and self.time_completed:
            return self.time_completed - self.time_started
        return None
