from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.permissions import require
from app.core.security import utcnow, iso_now

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    name: str
    sex: str = ""
    dob: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    bloodGroup: str = ""
    heightCm: Optional[float] = None
    weightKg: Optional[float] = None
    emergency: Optional[dict] = None


class AllergyIn(BaseModel):
    name: str
    reaction: str = ""
    severity: str = "Moderate"
    noted: str = ""


class ConditionIn(BaseModel):
    name: str
    since: str = ""
    status: str = "Active"


def _next_patient_id(db) -> str:
    # Simple sequential for demo
    return None  # filled in endpoint


@router.get("")
async def list_patients(
    q: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    require(user, "patients.read")
    db = get_db()
    filt: dict = {}
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"id": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    cursor = db.patients.find(filt).sort("name", 1)
    items = []
    async for p in cursor:
        p.pop("_id", None)
        items.append(p)
    return items


@router.post("")
async def create_patient(body: PatientCreate, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    count = await db.patients.count_documents({})
    pid = f"RPS-{1000 + count + 1}"
    doc = {
        "id": pid,
        "name": body.name,
        "sex": body.sex,
        "dob": body.dob,
        "phone": body.phone,
        "email": body.email,
        "address": body.address,
        "bloodGroup": body.bloodGroup,
        "heightCm": body.heightCm,
        "weightKg": body.weightKg,
        "emergency": body.emergency,
        "allergies": [],
        "conditions": [],
        "medications": [],
        "pastSurgeries": [],
        "familyHistory": "",
        "lifestyle": {"smoking": "", "alcohol": ""},
        "timeline": [{
            "id": 1,
            "date": iso_now()[:10],
            "type": "Registered",
            "title": "Registered at the centre",
            "by": user["name"],
        }],
        "allergiesRecorded": False,
        "createdAt": utcnow(),
        "createdBy": user["staffId"],
    }
    await db.patients.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/{patient_id}")
async def get_patient(patient_id: str, user: dict = Depends(get_current_user)):
    require(user, "patients.read")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    p.pop("_id", None)
    return p


@router.put("/{patient_id}")
async def update_patient(patient_id: str, body: PatientCreate, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    updates = body.model_dump(exclude_unset=True)
    updates["updatedAt"] = utcnow()
    await db.patients.update_one({"id": patient_id}, {"$set": updates})
    p = await db.patients.find_one({"id": patient_id})
    p.pop("_id", None)
    return p


# ---- Allergies ----
@router.get("/{patient_id}/allergies")
async def list_allergies(patient_id: str, user: dict = Depends(get_current_user)):
    require(user, "patients.read")
    p = await get_db().patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    return p.get("allergies", [])


@router.post("/{patient_id}/allergies")
async def add_allergy(patient_id: str, body: AllergyIn, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    allergies = p.get("allergies", [])
    new_id = max([a.get("id", 0) for a in allergies] or [0]) + 1
    item = {"id": new_id, **body.model_dump(), "noted": body.noted or iso_now()[:10], "by": user["name"]}
    allergies.append(item)
    await db.patients.update_one(
        {"id": patient_id},
        {"$set": {"allergies": allergies, "allergiesRecorded": True}},
    )
    return item


@router.delete("/{patient_id}/allergies/{item_id}")
async def delete_allergy(patient_id: str, item_id: int, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    allergies = [a for a in p.get("allergies", []) if a.get("id") != item_id]
    await db.patients.update_one({"id": patient_id}, {"$set": {"allergies": allergies}})
    return {"ok": True}


@router.post("/{patient_id}/allergies/confirm-none")
async def confirm_no_allergies(patient_id: str, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    await db.patients.update_one(
        {"id": patient_id},
        {"$set": {"allergies": [], "allergiesRecorded": True}},
    )
    return {"ok": True}


# ---- Conditions ----
@router.get("/{patient_id}/conditions")
async def list_conditions(patient_id: str, user: dict = Depends(get_current_user)):
    require(user, "patients.read")
    p = await get_db().patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    return p.get("conditions", [])


@router.post("/{patient_id}/conditions")
async def add_condition(patient_id: str, body: ConditionIn, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    conditions = p.get("conditions", [])
    new_id = max([c.get("id", 0) for c in conditions] or [0]) + 1
    item = {"id": new_id, **body.model_dump()}
    conditions.append(item)
    await db.patients.update_one({"id": patient_id}, {"$set": {"conditions": conditions}})
    return item


@router.delete("/{patient_id}/conditions/{item_id}")
async def delete_condition(patient_id: str, item_id: int, user: dict = Depends(get_current_user)):
    require(user, "patients.write")
    db = get_db()
    p = await db.patients.find_one({"id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail={"message": "Patient not found."})
    conditions = [c for c in p.get("conditions", []) if c.get("id") != item_id]
    await db.patients.update_one({"id": patient_id}, {"$set": {"conditions": conditions}})
    return {"ok": True}
