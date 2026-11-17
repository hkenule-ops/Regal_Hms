from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.permissions import can, require
from app.core.security import make_token, hash_token, utcnow, hash_password
from datetime import timedelta
from app.config import get_settings

router = APIRouter(prefix="/staff", tags=["staff"])


class StaffCreate(BaseModel):
    name: str
    title: str = ""
    email: EmailStr
    role: str
    department: Optional[str] = None
    isHead: bool = False
    phone: str = ""
    active: bool = True


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    department: Optional[str] = None
    isHead: Optional[bool] = None
    phone: Optional[str] = None
    active: Optional[bool] = None


def _public_staff(s: dict) -> dict:
    return {
        "id": s["staffId"],
        "staffId": s["staffId"],
        "name": s["name"],
        "title": s.get("title", ""),
        "email": s["email"],
        "role": s["role"],
        "department": s.get("department"),
        "isHead": bool(s.get("isHead") and s.get("active", True)),
        "phone": s.get("phone", ""),
        "active": s.get("active", True),
    }


@router.get("")
async def list_staff(user: dict = Depends(get_current_user)):
    require(user, "staff.read")
    db = get_db()
    cursor = db.staff.find({}).sort("name", 1)
    items = []
    async for s in cursor:
        items.append(_public_staff(s))
    return items


@router.get("/colleagues")
async def colleagues(user: dict = Depends(get_current_user)):
    """Active staff with accounts for pickers."""
    db = get_db()
    # Only those with activated accounts
    accounts = await db.accounts.find({"activated": True}).to_list(500)
    ids = {a["staffId"] for a in accounts}
    cursor = db.staff.find({"staffId": {"$in": list(ids)}, "active": True}).sort("name", 1)
    items = []
    async for s in cursor:
        items.append({
            "id": s["staffId"],
            "name": s["name"],
            "title": s.get("title", ""),
            "role": s["role"],
            "department": s.get("department"),
            "isHead": bool(s.get("isHead")),
        })
    return items


@router.get("/accounts")
async def staff_accounts(user: dict = Depends(get_current_user)):
    require(user, "staff.accounts")
    db = get_db()
    staff_list = await db.staff.find({}).to_list(500)
    accounts = {a["staffId"]: a for a in await db.accounts.find({}).to_list(500)}
    result = []
    for s in staff_list:
        if s["role"] == "director" and user["role"] != "director":
            # HR never sees director account details / links
            continue
        acc = accounts.get(s["staffId"], {})
        result.append({
            "staffId": s["staffId"],
            "name": s["name"],
            "email": s["email"],
            "role": s["role"],
            "active": s.get("active", True),
            "activated": acc.get("activated", False),
            "mfaEnrolled": bool(acc.get("mfa_secret")),
            "locked": bool(acc.get("locked_until") and acc["locked_until"] > utcnow()),
            "lastLogin": None,  # could join sessions
        })
    return result


@router.post("")
async def create_staff(body: StaffCreate, user: dict = Depends(get_current_user)):
    require(user, "staff.write")
    db = get_db()
    # Validate role
    if body.role in ("director", "hr") and user["role"] != "director":
        raise HTTPException(status_code=403, detail={"message": "Only the system administrator can create director or HR accounts."})
    existing = await db.staff.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail={"message": "Email already in use."})

    # Head uniqueness
    if body.isHead and body.department:
        other = await db.staff.find_one({"department": body.department, "isHead": True, "active": True})
        if other:
            raise HTTPException(status_code=409, detail={"message": f"Department {body.department} already has an active head."})

    # Generate ID
    count = await db.staff.count_documents({})
    staff_id = f"ST-{count + 1:02d}"
    doc = {
        "staffId": staff_id,
        "name": body.name,
        "title": body.title,
        "email": body.email.lower(),
        "role": body.role,
        "department": body.department if body.role not in ("director", "hr") else None,
        "isHead": body.isHead if body.role not in ("director", "hr") else False,
        "phone": body.phone,
        "active": body.active,
        "createdAt": utcnow(),
        "createdBy": user["staffId"],
    }
    await db.staff.insert_one(doc)
    # Create account shell (not activated)
    await db.accounts.insert_one({
        "staffId": staff_id,
        "email": body.email.lower(),
        "password_hash": None,
        "activated": False,
        "mfa_secret": None,
        "backup_codes_hashed": [],
        "trusted_devices": [],
        "failed_attempts": 0,
        "locked_until": None,
    })
    return _public_staff(doc)


@router.put("/{staff_id}")
async def update_staff(staff_id: str, body: StaffUpdate, user: dict = Depends(get_current_user)):
    require(user, "staff.write")
    db = get_db()
    staff = await db.staff.find_one({"staffId": staff_id})
    if not staff:
        raise HTTPException(status_code=404, detail={"message": "Staff not found."})
    if staff["role"] in ("director", "hr") and user["role"] != "director":
        raise HTTPException(status_code=403, detail={"message": "Cannot modify protected roles."})

    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if "email" in updates:
        updates["email"] = updates["email"].lower()
        conflict = await db.staff.find_one({"email": updates["email"], "staffId": {"$ne": staff_id}})
        if conflict:
            raise HTTPException(status_code=409, detail={"message": "Email already in use."})
    if updates.get("isHead") and updates.get("department", staff.get("department")):
        other = await db.staff.find_one({
            "department": updates.get("department", staff.get("department")),
            "isHead": True,
            "active": True,
            "staffId": {"$ne": staff_id},
        })
        if other:
            raise HTTPException(status_code=409, detail={"message": "Department already has an active head."})

    if updates:
        updates["updatedAt"] = utcnow()
        await db.staff.update_one({"staffId": staff_id}, {"$set": updates})
        if "email" in updates:
            await db.accounts.update_one({"staffId": staff_id}, {"$set": {"email": updates["email"]}})
        if updates.get("active") is False:
            await db.sessions.delete_many({"staffId": staff_id})

    staff = await db.staff.find_one({"staffId": staff_id})
    return _public_staff(staff)


@router.post("/{staff_id}/invite")
async def invite_staff(staff_id: str, user: dict = Depends(get_current_user)):
    require(user, "staff.accounts")
    db = get_db()
    settings = get_settings()
    staff = await db.staff.find_one({"staffId": staff_id})
    if not staff:
        raise HTTPException(status_code=404, detail={"message": "Staff not found."})
    account = await db.accounts.find_one({"staffId": staff_id})
    if not account:
        raise HTTPException(status_code=404, detail={"message": "Account record missing."})
    if account.get("activated"):
        raise HTTPException(status_code=400, detail={"message": "Account already activated."})

    token = make_token()
    await db.accounts.update_one(
        {"staffId": staff_id},
        {"$set": {
            "invite_token_hash": hash_token(token),
            "invite_token_expires": utcnow() + timedelta(hours=settings.invite_expiry_hours),
        }},
    )
    # Demo: print link
    print(f"[DEMO] Invite link for {staff['email']}: /activate?token={token}")
    return {"sent": True, "token": token if settings.environment == "development" else None}


@router.post("/{staff_id}/reset-password")
async def admin_reset_password(staff_id: str, user: dict = Depends(get_current_user)):
    require(user, "staff.accounts")
    db = get_db()
    settings = get_settings()
    account = await db.accounts.find_one({"staffId": staff_id})
    if not account:
        raise HTTPException(status_code=404, detail={"message": "Account not found."})
    token = make_token()
    await db.accounts.update_one(
        {"staffId": staff_id},
        {"$set": {
            "reset_token_hash": hash_token(token),
            "reset_token_expires": utcnow() + timedelta(minutes=settings.reset_expiry_minutes),
        }},
    )
    print(f"[DEMO] Reset link for {account['email']}: /reset?token={token}")
    return {"sent": True}


@router.post("/{staff_id}/reset-two-step")
async def reset_two_step(staff_id: str, user: dict = Depends(get_current_user)):
    require(user, "staff.accounts")
    db = get_db()
    await db.accounts.update_one(
        {"staffId": staff_id},
        {"$set": {
            "mfa_secret": None,
            "backup_codes_hashed": [],
            "trusted_devices": [],
        }},
    )
    await db.sessions.delete_many({"staffId": staff_id})
    return {"ok": True}


@router.post("/{staff_id}/unlock")
async def unlock_account(staff_id: str, user: dict = Depends(get_current_user)):
    require(user, "staff.accounts")
    db = get_db()
    await db.accounts.update_one(
        {"staffId": staff_id},
        {"$set": {"failed_attempts": 0, "locked_until": None}},
    )
    return {"ok": True}
