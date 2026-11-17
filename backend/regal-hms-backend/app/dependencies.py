from fastapi import Request, HTTPException, Depends
from app.database import get_db
from app.core.security import utcnow
from app.config import get_settings
from datetime import timedelta


async def get_current_user(request: Request) -> dict:
    """Load the signed-in staff from the session cookie. Raises 401 if missing/expired."""
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail={"message": "Not signed in."})

    db = get_db()
    session = await db.sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=401, detail={"message": "Session expired or invalid."})

    expires = session.get("expires_at")
    if expires and expires.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        await db.sessions.delete_one({"session_id": session_id})
        raise HTTPException(status_code=401, detail={"message": "Session expired."})

    staff = await db.staff.find_one({"staffId": session["staffId"], "active": True})
    if not staff:
        await db.sessions.delete_one({"session_id": session_id})
        raise HTTPException(status_code=401, detail={"message": "Account inactive or not found."})

    # Sliding expiry
    new_expires = utcnow() + timedelta(seconds=settings.session_max_age)
    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"expires_at": new_expires, "last_seen": utcnow()}},
    )

    return {
        "staffId": staff["staffId"],
        "name": staff["name"],
        "title": staff.get("title", ""),
        "email": staff["email"],
        "role": staff["role"],
        "department": staff.get("department"),
        "isHead": bool(staff.get("isHead") and staff.get("active")),
    }


async def get_optional_user(request: Request) -> dict | None:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
