# app/schemas/vehicles.py
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Vehicles ---
class VehicleBase(BaseModel):
    id: str = Field(..., description="Unique vehicle identifier")
    name: str = Field(..., description="Vehicle display name")


# --- Versions ---
class VersionBase(BaseModel):
    id: str = Field(..., description="Unique version identifier")
    name: str = Field(..., description="Version display name")
    type: Literal["beta", "stable", "dev_tag", "latest"] = Field(
        ..., description="Version type classification"
    )
    remote_name: Optional[str] = Field(
        None, description="Git remote name"
    )
    commit_ref: Optional[str] = Field(
        None, description="Git reference (tag, branch name, or commit SHA)"
    )


class VersionOut(VersionBase):
    vehicle_name: str = Field(
        ..., description="Vehicle name (e.g., 'copter', 'plane')"
    )


# --- Boards ---
class BoardBase(BaseModel):
    id: str = Field(..., description="Unique board identifier")
    name: str = Field(..., description="Board display name")


class BoardOut(BoardBase):
    vehicle_name: str = Field(..., description="Associated vehicle name")
    version_id: str = Field(..., description="Associated version identifier")


# --- Features ---
class CategoryBase(BaseModel):
    id: str = Field(..., description="Unique category identifier")
    name: str = Field(..., description="Category display name")
    description: Optional[str] = Field(
        None, description="Category description"
    )


class FeatureBase(BaseModel):
    id: str = Field(..., description="Unique feature identifier/flag name")
    name: str = Field(..., description="Feature display name")
    category: CategoryBase = Field(..., description="Feature category")
    defaultEnabled: bool = Field(
        ..., description="Whether feature is enabled by default"
    )
    description: Optional[str] = Field(
        None, description="Feature description"
    )


class FeatureOut(FeatureBase):
    vehicle_name: str = Field(..., description="Associated vehicle name")
    version_id: str = Field(..., description="Associated version identifier")


# --- Defaults ---
class DefaultsBase(BaseModel):
    feature_id: str = Field(..., description="Feature identifier/flag name")
    enabled: bool = Field(
        ..., description="Whether feature is enabled for this board"
    )


class DefaultsOut(DefaultsBase):
    vehicle_name: str = Field(..., description="Associated vehicle name")
    version_id: str = Field(..., description="Associated version identifier")
    board_id: str = Field(..., description="Associated board identifier")
