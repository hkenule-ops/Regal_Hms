from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.permissions import require
from app.core.security import utcnow, iso_now

router = APIRouter(prefix="/appointments", tags=["appointments"])

DAY_START = 8 * 60   # 08:00
DAY_END = 18 * 60    # 18:00


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _is_sunday(date_str: str) -> bool:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.weekday() == 6


class AppointmentCreate(BaseModel):
    patientId: str
    type: str
    clinicianId: str
    date: str
    start: str
    duration: int = 30
    notes: str = ""
    status: str = "Confirmed"


@router.get("")
async def list_appointments(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    patientId: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    require(user, "appointments.read")
    db = get_db()
    filt: dict = {}
    if from_ and to:
        filt["date"] = {"$gte": from_, "$lte": to}
    elif from_:
        filt["date"] = {"$gte": from_}
    if patientId:
        filt["patientId"] = patientId
    cursor = db.appointments.find(filt).sort([("date", 1), ("start", 1)])
    items = []
    async for a in cursor:
        a.pop("_id", None)
        items.append(a)
    return items


@router.post("")
async def create_appointment(body: AppointmentCreate, user: dict = Depends(get_current_user)):
    require(user, "appointments.write")
    db = get_db()

    if _is_sunday(body.date):
        raise HTTPException(status_code=400, detail={"message": "The centre is closed on Sundays."})

    start_m = _time_to_min(body.start)
    end_m = start_m + body.duration
    if start_m < DAY_START or end_m > DAY_END:
        raise HTTPException(status_code=400, detail={"message": "Appointment must be within opening hours (08:00–18:00)."})

    # Double-booking check for clinician
    existing = await db.appointments.find({
        "clinicianId": body.clinicianId,
        "date": body.date,
        "status": {"$ne": "Cancelled"},
    }).to_list(50)
    for e in existing:
        e_start = _time_to_min(e["start"])
        e_end = e_start + e.get("duration", 30)
        if start_m < e_end and end_m > e_start:
            raise HTTPException(status_code=409, detail={"message": "Clinician already has an appointment in that slot."})

    patient = await db.patients.find_one({"id": body.patientId})
    if not patient:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})

    count = await db.appointments.count_documents({})
    aid = f"A-{count + 1}"
    doc = {
        "id": aid,
        "patientId": body.patientId,
        "patient": patient["name"],
        "type": body.type,
        "clinicianId": body.clinicianId,
        "date": body.date,
        "start": body.start,
        "duration": body.duration,
        "status": body.status,
        "notes": body.notes,
        "createdAt": utcnow(),
        "createdBy": user["staffId"],
    }
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/{appt_id}")
async def get_appointment(appt_id: str, user: dict = Depends(get_current_user)):
    require(user, "appointments.read")
    a = await get_db().appointments.find_one({"id": appt_id})
    if not a:
        raise HTTPException(status_code=404, detail={"message": "Appointment not found."})
    a.pop("_id", None)
    return a


@router.put("/{appt_id}")
async def update_appointment(appt_id: str, body: AppointmentCreate, user: dict = Depends(get_current_user)):
    require(user, "appointments.write")
    db = get_db()
    a = await db.appointments.find_one({"id": appt_id})
    if not a:
        raise HTTPException(status_code=404, detail={"message": "Appointment not found."})
    updates = body.model_dump(exclude_unset=True)
    if "patientId" in updates:
        patient = await db.patients.find_one({"id": updates["patientId"]})
        if patient:
            updates["patient"] = patient["name"]
    updates["updatedAt"] = utcnow()
    await db.appointments.update_one({"id": appt_id}, {"$set": updates})
    a = await db.appointments.find_one({"id": appt_id})
    a.pop("_id", None)
    return a


@router.delete("/{appt_id}")
async def cancel_appointment(appt_id: str, user: dict = Depends(get_current_user)):
    require(user, "appointments.write")
    db = get_db()
    result = await db.appointments.update_one(
        {"id": appt_id},
        {"$set": {"status": "Cancelled", "cancelledAt": utcnow(), "cancelledBy": user["staffId"]}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail={"message": "Appointment not found."})
    return {"ok": True}
