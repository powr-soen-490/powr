# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for the invite endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateInviteRequest(BaseModel):
    email: EmailStr


class CreateInviteResponse(BaseModel):
    invite_id: UUID
    email: EmailStr
    role: str
    expires_at: datetime
    # Shown once: only its hash is stored, so a lost link has to be re-created.
    token: str
    accept_path: str


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=255)
    password: str
    eula_accepted: bool = False
    eula_version: str = Field(default="1.0", max_length=50)


class AcceptInviteResponse(BaseModel):
    user_id: UUID
    restaurant_id: UUID
    email: EmailStr
    role: str
    message: str = "Account created. You can now log in."


class RevokeInviteResponse(BaseModel):
    message: str = "Invite revoked."
