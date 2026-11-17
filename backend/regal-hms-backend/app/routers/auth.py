from fastapi import APIRouter, Request, Response, HTTPException, Depends
from datetime import timedelta
from app.database import get_db
from app.dependencies import get_current_user
from app.models.auth import (
    LoginRequest, MfaVerifyRequest, ConfirmEnrolRequest,
    ForgotPasswordRequest, ResetPasswordRequest, ActivateRequest,
    ChangePasswordRequest, LoginStepResponse, BackupCodesResponse,
)
from app.models.common import UserMe, OkResponse
from app.core.security import (
    verify_password, hash_password, make_session_id, make_challenge,
    make_token, hash_token, generate_totp_secret, totp_uri, verify_totp,
    make_backup_codes, hash_backup_code, utcnow, iso_now,
)
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


async def _audit(db, action: str, staff_id: str | None = None, detail: dict | None = None, ip: str | None = None):
    await db.audit_log.insert_one({
        "action": action,
        "staffId": staff_id,
        "detail": detail or {},
        "ip": ip,
        "at": utcnow(),
    })


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    """Start login. Returns MFA step or enrolment step. Same error for unknown/wrong password."""
    db = get_db()
    settings = get_settings()
    account = await db.accounts.find_one({"email": body.email.lower()})
    # Always same generic error
    bad = HTTPException(status_code=400, detail={"message": "Invalid email or password."})

    if not account:
        await _audit(db, "login_failed", detail={"email": body.email}, ip=request.client.host if request.client else None)
        raise bad

    # Lockout
    if account.get("locked_until") and account["locked_until"] > utcnow():
        raise HTTPException(status_code=400, detail={"message": "Account temporarily locked. Try again later."})

    if not verify_password(body.password, account["password_hash"]):
        fails = account.get("failed_attempts", 0) + 1
        update = {"failed_attempts": fails}
        if fails >= settings.max_failed_attempts:
            update["locked_until"] = utcnow() + timedelta(minutes=settings.lockout_minutes)
            update["failed_attempts"] = 0
        await db.accounts.update_one({"_id": account["_id"]}, {"$set": update})
        await _audit(db, "login_failed", staff_id=account.get("staffId"), ip=request.client.host if request.client else None)
        raise bad

    # Reset fails
    await db.accounts.update_one({"_id": account["_id"]}, {"$set": {"failed_attempts": 0, "locked_until": None}})

    staff = await db.staff.find_one({"staffId": account["staffId"], "active": True})
    if not staff:
        raise bad

    # Trusted device cookie skips MFA
    trusted = request.cookies.get("regal_trusted")
    if trusted and account.get("trusted_devices"):
        for td in account["trusted_devices"]:
            if td.get("token_hash") == hash_token(trusted) and td.get("expires_at", utcnow()) > utcnow():
                # Create session directly
                return await _create_session(db, response, staff, request, remember=False)

    challenge = make_challenge()
    challenge_doc = {
        "challenge": challenge,
        "staffId": staff["staffId"],
        "email": staff["email"],
        "type": "login",
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(minutes=10),
    }

    if not account.get("mfa_secret"):
        # First time: enrol
        secret = generate_totp_secret()
        challenge_doc["secret"] = secret
        challenge_doc["type"] = "enrol"
        await db.challenges.insert_one(challenge_doc)
        return LoginStepResponse(
            step="enrol",
            challenge=challenge,
            secret=secret,
            uri=totp_uri(secret, staff["email"]),
        )

    await db.challenges.insert_one(challenge_doc)
    return LoginStepResponse(step="mfa", challenge=challenge)


async def _create_session(db, response: Response, staff: dict, request: Request, remember: bool = False):
    settings = get_settings()
    session_id = make_session_id()
    expires = utcnow() + timedelta(seconds=settings.session_max_age)
    await db.sessions.insert_one({
        "session_id": session_id,
        "staffId": staff["staffId"],
        "created_at": utcnow(),
        "expires_at": expires,
        "last_seen": utcnow(),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    })
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.session_max_age,
        path="/",
    )
    if remember:
        token = make_token()
        await db.accounts.update_one(
            {"staffId": staff["staffId"]},
            {"$push": {"trusted_devices": {
                "token_hash": hash_token(token),
                "created_at": utcnow(),
                "expires_at": utcnow() + timedelta(seconds=settings.trusted_device_max_age),
                "user_agent": request.headers.get("user-agent"),
            }}},
        )
        response.set_cookie(
            key="regal_trusted",
            value=token,
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            max_age=settings.trusted_device_max_age,
            path="/",
        )
    await _audit(db, "login_success", staff_id=staff["staffId"], ip=request.client.host if request.client else None)
    return {
        "staffId": staff["staffId"],
        "name": staff["name"],
        "title": staff.get("title", ""),
        "email": staff["email"],
        "role": staff["role"],
        "department": staff.get("department"),
        "isHead": bool(staff.get("isHead") and staff.get("active")),
    }


@router.post("/verify-mfa")
async def verify_mfa(body: MfaVerifyRequest, request: Request, response: Response):
    db = get_db()
    ch = await db.challenges.find_one({"challenge": body.challenge, "type": "login"})
    if not ch or ch["expires_at"] < utcnow():
        raise HTTPException(status_code=400, detail={"message": "Challenge expired or invalid."})

    account = await db.accounts.find_one({"staffId": ch["staffId"]})
    if not account:
        raise HTTPException(status_code=400, detail={"message": "Invalid challenge."})

    ok = False
    if verify_totp(account["mfa_secret"], body.code):
        ok = True
    else:
        # Backup codes
        code_hash = hash_backup_code(body.code)
        codes = account.get("backup_codes_hashed", [])
        if code_hash in codes:
            ok = True
            codes.remove(code_hash)
            await db.accounts.update_one({"_id": account["_id"]}, {"$set": {"backup_codes_hashed": codes}})

    if not ok:
        fails = account.get("failed_attempts", 0) + 1
        update = {"failed_attempts": fails}
        settings = get_settings()
        if fails >= settings.max_failed_attempts:
            update["locked_until"] = utcnow() + timedelta(minutes=settings.lockout_minutes)
            update["failed_attempts"] = 0
        await db.accounts.update_one({"_id": account["_id"]}, {"$set": update})
        raise HTTPException(status_code=400, detail={"message": "Invalid code."})

    await db.challenges.delete_one({"challenge": body.challenge})
    staff = await db.staff.find_one({"staffId": ch["staffId"]})
    return await _create_session(db, response, staff, request, remember=body.remember)


@router.post("/confirm-enrolment", response_model=BackupCodesResponse)
async def confirm_enrolment(body: ConfirmEnrolRequest, request: Request, response: Response):
    db = get_db()
    ch = await db.challenges.find_one({"challenge": body.challenge, "type": "enrol"})
    if not ch or ch["expires_at"] < utcnow():
        raise HTTPException(status_code=400, detail={"message": "Challenge expired or invalid."})

    if not verify_totp(ch["secret"], body.code):
        raise HTTPException(status_code=400, detail={"message": "Invalid authenticator code."})

    codes = make_backup_codes(8)
    hashed = [hash_backup_code(c) for c in codes]
    await db.accounts.update_one(
        {"staffId": ch["staffId"]},
        {"$set": {
            "mfa_secret": ch["secret"],
            "backup_codes_hashed": hashed,
            "mfa_enrolled_at": utcnow(),
        }},
    )
    await db.challenges.delete_one({"challenge": body.challenge})
    staff = await db.staff.find_one({"staffId": ch["staffId"]})
    await _create_session(db, response, staff, request, remember=body.remember)
    return BackupCodesResponse(codes=codes)


@router.get("/me", response_model=UserMe)
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        await get_db().sessions.delete_one({"session_id": session_id})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return OkResponse()


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Always returns {sent: true}. Never reveals if email exists."""
    db = get_db()
    settings = get_settings()
    account = await db.accounts.find_one({"email": body.email.lower()})
    if account:
        token = make_token()
        await db.accounts.update_one(
            {"_id": account["_id"]},
            {"$set": {
                "reset_token_hash": hash_token(token),
                "reset_token_expires": utcnow() + timedelta(minutes=settings.reset_expiry_minutes),
            }},
        )
        # In production: send email with link containing token
        # For demo we log it
        print(f"[DEMO] Password reset token for {body.email}: {token}")
        await _audit(db, "password_reset_requested", staff_id=account.get("staffId"))
    return {"sent": True}


@router.get("/reset/{token}")
async def validate_reset(token: str):
    db = get_db()
    account = await db.accounts.find_one({
        "reset_token_hash": hash_token(token),
        "reset_token_expires": {"$gt": utcnow()},
    })
    if not account:
        raise HTTPException(status_code=400, detail={"message": "Invalid or expired reset link."})
    return {"valid": True, "email": account["email"]}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    db = get_db()
    account = await db.accounts.find_one({
        "reset_token_hash": hash_token(body.token),
        "reset_token_expires": {"$gt": utcnow()},
    })
    if not account:
        raise HTTPException(status_code=400, detail={"message": "Invalid or expired reset link."})
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail={"message": "Password must be at least 8 characters."})
    await db.accounts.update_one(
        {"_id": account["_id"]},
        {"$set": {
            "password_hash": hash_password(body.password),
            "reset_token_hash": None,
            "reset_token_expires": None,
            "trusted_devices": [],  # revoke trusted devices
            "failed_attempts": 0,
            "locked_until": None,
        }},
    )
    # Kill all sessions
    await db.sessions.delete_many({"staffId": account["staffId"]})
    await _audit(db, "password_reset_completed", staff_id=account["staffId"])
    return OkResponse()


@router.get("/invite/{token}")
async def validate_invite(token: str):
    db = get_db()
    account = await db.accounts.find_one({
        "invite_token_hash": hash_token(token),
        "invite_token_expires": {"$gt": utcnow()},
        "activated": {"$ne": True},
    })
    if not account:
        raise HTTPException(status_code=400, detail={"message": "Invalid or expired invitation."})
    staff = await db.staff.find_one({"staffId": account["staffId"]})
    return {
        "valid": True,
        "email": account["email"],
        "name": staff["name"] if staff else "",
        "role": staff["role"] if staff else "",
    }


@router.post("/activate")
async def activate(body: ActivateRequest, request: Request, response: Response):
    db = get_db()
    account = await db.accounts.find_one({
        "invite_token_hash": hash_token(body.token),
        "invite_token_expires": {"$gt": utcnow()},
        "activated": {"$ne": True},
    })
    if not account:
        raise HTTPException(status_code=400, detail={"message": "Invalid or expired invitation."})
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail={"message": "Password must be at least 8 characters."})
    if not body.acknowledged:
        raise HTTPException(status_code=400, detail={"message": "You must acknowledge the terms."})

    secret = generate_totp_secret()
    await db.accounts.update_one(
        {"_id": account["_id"]},
        {"$set": {
            "password_hash": hash_password(body.password),
            "activated": True,
            "activated_at": utcnow(),
            "invite_token_hash": None,
            "invite_token_expires": None,
            "mfa_secret": None,  # will enrol next
        }},
    )
    # Return enrol step
    challenge = make_challenge()
    await db.challenges.insert_one({
        "challenge": challenge,
        "staffId": account["staffId"],
        "email": account["email"],
        "type": "enrol",
        "secret": secret,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(minutes=15),
    })
    staff = await db.staff.find_one({"staffId": account["staffId"]})
    return LoginStepResponse(
        step="enrol",
        challenge=challenge,
        secret=secret,
        uri=totp_uri(secret, account["email"]),
    )


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    account = await db.accounts.find_one({"staffId": user["staffId"]})
    if not account or not verify_password(body.current, account["password_hash"]):
        raise HTTPException(status_code=400, detail={"message": "Current password is incorrect."})
    if len(body.next) < 8:
        raise HTTPException(status_code=400, detail={"message": "New password must be at least 8 characters."})
    await db.accounts.update_one(
        {"_id": account["_id"]},
        {"$set": {
            "password_hash": hash_password(body.next),
            "trusted_devices": [],
        }},
    )
    # Kill other sessions
    await db.sessions.delete_many({"staffId": user["staffId"]})
    await _audit(db, "password_changed", staff_id=user["staffId"])
    return OkResponse()
