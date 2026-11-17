from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MfaVerifyRequest(BaseModel):
    challenge: str
    code: str
    remember: bool = False


class ConfirmEnrolRequest(BaseModel):
    challenge: str
    code: str
    remember: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ActivateRequest(BaseModel):
    token: str
    password: str
    acknowledged: bool = True


class ChangePasswordRequest(BaseModel):
    current: str
    next: str


class LoginStepResponse(BaseModel):
    step: str  # mfa | enrol
    challenge: str
    secret: Optional[str] = None
    uri: Optional[str] = None


class BackupCodesResponse(BaseModel):
    codes: List[str]
