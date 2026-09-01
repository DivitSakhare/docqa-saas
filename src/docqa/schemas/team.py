import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from docqa.models.user import UserRole


class TeamMemberCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.MEMBER


class TeamMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    role: str
    created_at: datetime
