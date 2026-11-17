"""
Permission helpers. Mirror of frontend src/utils/permissions.js.
Server is the authority — never trust client role.
"""

ROLES = ("director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance", "hr")
DEPARTMENTS = ("frontdesk", "clinic", "theatre", "aftercare", "laboratory", "pharmacy", "finance")

# Module / action → allowed roles
PERMISSIONS = {
    "patients.read": ["director", "surgeon", "nurse", "frontdesk"],
    "patients.write": ["director", "surgeon", "nurse", "frontdesk"],
    "appointments.read": ["director", "surgeon", "nurse", "frontdesk"],
    "appointments.write": ["director", "surgeon", "nurse", "frontdesk"],
    "consultations.read": ["director", "surgeon", "nurse"],
    "consultations.write": ["director", "surgeon"],
    "surgical_plans.read": ["director", "surgeon", "nurse"],
    "surgical_plans.write": ["director", "surgeon", "nurse"],
    "surgeries.read": ["director", "surgeon", "nurse"],
    "surgeries.write": ["director", "surgeon", "nurse"],
    "aftercare.read": ["director", "surgeon", "nurse"],
    "aftercare.write": ["director", "surgeon", "nurse"],
    "aftercare.review_flag": ["director", "surgeon"],
    "aftercare.discharge": ["director", "surgeon"],
    "lab.read": ["director", "surgeon", "nurse", "pharmacist"],
    "lab.request": ["director", "surgeon", "nurse"],  # + department pairing rules
    "lab.work": ["nurse"],  # laboratory staff only (checked with department)
    "lab.review": ["director", "surgeon"],
    "pharmacy.read": ["director", "surgeon", "nurse", "pharmacist"],
    "pharmacy.write": ["director", "pharmacist"],
    "pharmacy.dispense": ["pharmacist"],
    "billing.read": ["director", "finance", "frontdesk"],
    "billing.money": ["director", "finance"],
    "billing.write": ["director", "finance", "frontdesk"],
    "staff.read": ["director", "hr"],
    "staff.write": ["hr"],
    "staff.accounts": ["hr"],
    "tasks.read": ["director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance", "hr"],
    "tasks.write": ["director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance", "hr"],
    "messages": ["director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance", "hr"],
    "reports.department": ["director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance"],
    "reports.money": ["director", "finance"],
    "dashboard": ["director", "surgeon", "nurse", "pharmacist", "frontdesk", "finance", "hr"],
}


def can(user: dict, action: str) -> bool:
    if not user:
        return False
    role = user.get("role")
    allowed = PERMISSIONS.get(action, [])
    return role in allowed


def require(user: dict, action: str) -> None:
    from fastapi import HTTPException
    if not can(user, action):
        raise HTTPException(status_code=403, detail={"message": "You do not have permission for this action."})
