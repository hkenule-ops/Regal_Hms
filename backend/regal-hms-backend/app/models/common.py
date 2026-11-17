from pydantic import BaseModel, Field, EmailStr
from typing import Any, Optional
from datetime import datetime


class MessageResponse(BaseModel):
    message: str


class OkResponse(BaseModel):
    ok: bool = True


class StaffPublic(BaseModel):
    staffId: str
    name: str
    title: str = ""
    email: EmailStr
    role: str
    department: Optional[str] = None
    isHead: bool = False


class UserMe(StaffPublic):
    pass
