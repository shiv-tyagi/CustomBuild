from typing import Optional, List, Dict
from datetime import datetime

from pydantic import BaseModel, Field


# --- Refresh Remotes Response ---
class RefreshRemotesResponse(BaseModel):
    """Response schema for remote refresh operation."""
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Human-readable status message")
    triggered_at: float = Field(
        ..., description="Unix timestamp when refresh was triggered"
    )
    remotes_refreshed: List[str] = Field(
        default_factory=list,
        description="List of remote names that were refreshed"
    )
    errors: Optional[Dict[str, str]] = Field(
        None,
        description="Errors encountered per remote (if any)"
    )

    @property
    def triggered_datetime(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.triggered_at)
