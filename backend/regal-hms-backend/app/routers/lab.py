from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, Any
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.permissions import require, can
from app.core.security import utcnow, iso_now

router = APIRouter(prefix="/lab-requests", tags=["laboratory"])

OPEN = ["Requested", "Collected"]


class LabCreate(BaseModel):
    patientId: str
    test: str
    priority: str = "Routine"
    clinicalNote: str = ""
    consultationId: Optional[str] = None
    source: str = "Manual"


class LabUpdate(BaseModel):
    status: Optional[str] = None
    sampleNote: Optional[str] = None
    results: Optional[dict] = None
    reviewNote: Optional[str] = None
    cancelReason: Optional[str] = None


def _is_lab_staff(user: dict) -> bool:
    return user.get("department") == "laboratory" and user["role"] in ("nurse", "surgeon")


@router.get("")
async def list_lab(
    status: Optional[str] = None,
    patientId: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    require(user, "lab.read")
    db = get_db()
    filt: dict = {}
    if status:
        filt["status"] = status
    if patientId:
        filt["patientId"] = patientId
    cursor = db.lab_requests.find(filt).sort("requestedAt", -1)
    items = []
    async for r in cursor:
        r.pop("_id", None)
        items.append(r)
    return items


@router.post("")
async def create_lab(body: LabCreate, user: dict = Depends(get_current_user)):
    if not can(user, "lab.request"):
        raise HTTPException(status_code=403, detail={"message": "You cannot request lab tests."})
    # Simple pairing: pharmacy cannot request lab
    if user.get("department") == "pharmacy":
        raise HTTPException(status_code=403, detail={"message": "Pharmacy is not paired with the laboratory for requests."})
    db = get_db()
    patient = await db.patients.find_one({"id": body.patientId})
    if not patient:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    count = await db.lab_requests.count_documents({})
    lid = f"L-{7000 + count + 1}"
    doc = {
        "id": lid,
        "patientId": body.patientId,
        "patient": patient["name"],
        "sex": patient.get("sex", ""),
        "test": body.test,
        "priority": body.priority,
        "requestedBy": user["name"],
        "requestedById": user["staffId"],
        "requestedByDept": user.get("department"),
        "requestedAt": iso_now(),
        "consultationId": body.consultationId,
        "source": body.source,
        "clinicalNote": body.clinicalNote,
        "status": "Requested",
        "takenById": "",
        "takenByName": "",
        "takenAt": None,
        "collectedAt": None,
        "collectedBy": "",
        "sampleNote": "",
        "results": {},
        "resultedAt": None,
        "resultedById": "",
        "resultedBy": "",
        "reviewedAt": None,
        "reviewedBy": "",
        "reviewNote": "",
        "cancelReason": "",
    }
    await db.lab_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/{lab_id}/take")
async def take_request(lab_id: str, user: dict = Depends(get_current_user)):
    if not _is_lab_staff(user):
        raise HTTPException(status_code=403, detail={"message": "Only laboratory staff can take requests from the queue."})
    db = get_db()
    lab = await db.lab_requests.find_one({"id": lab_id})
    if not lab:
        raise HTTPException(status_code=404, detail={"message": "Lab request not found."})
    if lab["status"] not in OPEN:
        raise HTTPException(status_code=400, detail={"message": "Request is not open."})
    if lab.get("takenById"):
        raise HTTPException(status_code=409, detail={"message": f"{lab.get('takenByName') or 'Someone'} already took this request."})
    await db.lab_requests.update_one(
        {"id": lab_id},
        {"$set": {"takenById": user["staffId"], "takenByName": user["name"], "takenAt": iso_now()}},
    )
    lab = await db.lab_requests.find_one({"id": lab_id})
    lab.pop("_id", None)
    return lab


@router.post("/{lab_id}/release")
async def release_request(lab_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    lab = await db.lab_requests.find_one({"id": lab_id})
    if not lab:
        raise HTTPException(status_code=404, detail={"message": "Lab request not found."})
    is_taker = lab.get("takenById") == user["staffId"]
    is_head = user.get("department") == "laboratory" and user.get("isHead")
    if not (is_taker or is_head):
        raise HTTPException(status_code=403, detail={"message": "Only the person who took it, or the laboratory head, can release it."})
    await db.lab_requests.update_one(
        {"id": lab_id},
        {"$set": {"takenById": "", "takenByName": "", "takenAt": None}},
    )
    lab = await db.lab_requests.find_one({"id": lab_id})
    lab.pop("_id", None)
    return lab


@router.put("/{lab_id}")
async def update_lab(lab_id: str, body: LabUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    lab = await db.lab_requests.find_one({"id": lab_id})
    if not lab:
        raise HTTPException(status_code=404, detail={"message": "Lab request not found."})

    status = body.status
    if not status:
        raise HTTPException(status_code=400, detail={"message": "status is required."})

    updates: dict[str, Any] = {"status": status}

    if status in ("Collected", "Resulted"):
        if not _is_lab_staff(user):
            raise HTTPException(status_code=403, detail={"message": "Only laboratory staff can perform lab work."})
        if lab.get("takenById") != user["staffId"]:
            raise HTTPException(status_code=403, detail={"message": "Take this request from the queue first."})
        if status == "Collected":
            updates["collectedAt"] = iso_now()
            updates["collectedBy"] = user["name"]
            if body.sampleNote is not None:
                updates["sampleNote"] = body.sampleNote
        if status == "Resulted":
            if not body.results:
                raise HTTPException(status_code=400, detail={"message": "Results are required."})
            updates["results"] = body.results
            updates["resultedAt"] = iso_now()
            updates["resultedById"] = user["staffId"]
            updates["resultedBy"] = user["name"]

    elif status == "Reviewed":
        if user["role"] not in ("surgeon", "director"):
            raise HTTPException(status_code=403, detail={"message": "Only a surgeon or the Medical Director can review results."})
        if lab.get("resultedById") == user["staffId"]:
            raise HTTPException(status_code=403, detail={"message": "You cannot sign off results you entered."})
        updates["reviewedAt"] = iso_now()
        updates["reviewedBy"] = user["name"]
        if body.reviewNote:
            updates["reviewNote"] = body.reviewNote

    elif status == "Cancelled":
        if user["role"] not in ("surgeon", "director"):
            raise HTTPException(status_code=403, detail={"message": "Only a surgeon or the Medical Director can cancel."})
        updates["cancelReason"] = body.cancelReason or ""

    else:
        raise HTTPException(status_code=400, detail={"message": f"Unknown status transition: {status}"})

    await db.lab_requests.update_one({"id": lab_id}, {"$set": updates})
    lab = await db.lab_requests.find_one({"id": lab_id})
    lab.pop("_id", None)
    return lab
