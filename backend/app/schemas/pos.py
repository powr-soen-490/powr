# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for POS credentials endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PosProvider = Literal["TOAST", "SQUARE"]


class PosCredentialsRequest(BaseModel):
    pos_name: PosProvider
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    # On PATCH, omitted/null token and expiry leave the stored values unchanged.
    access_token: str | None = Field(default=None, min_length=1)
    expires_at: datetime | None = None


class PosCredentialsResponse(BaseModel):
    id: UUID
    pos_name: str
    client_id: str
    expires_at: datetime | None


class SetPosResponse(BaseModel):
    message: str
