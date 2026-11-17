"""
Seed MongoDB with demo data compatible with the Regal HMS frontend.
Run: python seed.py
Requires MongoDB running and MONGODB_URI in env (default localhost).
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import os

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "regal_hms")


def hash_pw(p: str) -> str:
    return pwd_context.hash(p)


async def main():
    client = AsyncIOMotorClient(URI)
    db = client[DB_NAME]
    print(f"Seeding {DB_NAME} ...")

    # Clear
    for col in ["staff", "accounts", "patients", "appointments", "sessions", "challenges",
                "surgeries", "consultations", "surgical_plans", "aftercare", "lab_requests",
                "prescriptions", "medications", "quotations", "invoices", "payments",
                "tasks", "message_threads", "messages", "audit_log"]:
        await db[col].delete_many({})

    now = datetime.now(timezone.utc)

    staff = [
        {"staffId": "ST-01", "name": "Dr. Amadi", "title": "Consultant Plastic Surgeon", "email": "amadi@regal.example",
         "role": "surgeon", "department": "clinic", "isHead": True, "phone": "0801", "active": True},
        {"staffId": "ST-02", "name": "Dr. Bello", "title": "Consultant Plastic Surgeon", "email": "bello@regal.example",
         "role": "surgeon", "department": "theatre", "isHead": True, "phone": "0802", "active": True},
        {"staffId": "ST-03", "name": "Dr. Okon", "title": "Medical Director", "email": "director@regal.example",
         "role": "director", "department": None, "isHead": False, "phone": "0803", "active": True},
        {"staffId": "ST-04", "name": "Nurse Joy", "title": "Theatre and recovery nurse", "email": "joy@regal.example",
         "role": "nurse", "department": "aftercare", "isHead": True, "phone": "0804", "active": True},
        {"staffId": "ST-05", "name": "Nurse Chioma", "title": "Clinic nurse", "email": "chioma@regal.example",
         "role": "nurse", "department": "clinic", "isHead": False, "phone": "0805", "active": True},
        {"staffId": "ST-06", "name": "Adaeze Okafor", "title": "Pharmacist", "email": "adaeze@regal.example",
         "role": "pharmacist", "department": "pharmacy", "isHead": True, "phone": "0806", "active": True},
        {"staffId": "ST-07", "name": "Front Desk Amina", "title": "Receptionist", "email": "amina@regal.example",
         "role": "frontdesk", "department": "frontdesk", "isHead": True, "phone": "0807", "active": True},
        {"staffId": "ST-08", "name": "Finance Tunde", "title": "Accounts officer", "email": "tunde@regal.example",
         "role": "finance", "department": "finance", "isHead": True, "phone": "0808", "active": True},
        {"staffId": "ST-09", "name": "HR Funke", "title": "Staff Administrator", "email": "funke@regal.example",
         "role": "hr", "department": None, "isHead": False, "phone": "0809", "active": True},
        {"staffId": "ST-10", "name": "Lab Tech Emeka", "title": "Laboratory nurse", "email": "emeka@regal.example",
         "role": "nurse", "department": "laboratory", "isHead": True, "phone": "0810", "active": True},
    ]
    await db.staff.insert_many(staff)

    # Password for all demo accounts: Password1!
    # MFA is pre-enrolled with a known secret for testing (use any authenticator with the secret below, or we skip for seed)
    # For simplicity in seed we set mfa_secret so login goes to MFA step.
    # Demo TOTP secret (base32): JBSWY3DPEHPK3PXP  → codes change every 30s; for testing you can temporarily disable MFA or use a library.
    demo_secret = "JBSWY3DPEHPK3PXP"
    accounts = []
    for s in staff:
        accounts.append({
            "staffId": s["staffId"],
            "email": s["email"],
            "password_hash": hash_pw("Password1!"),
            "activated": True,
            "mfa_secret": demo_secret,
            "backup_codes_hashed": [],
            "trusted_devices": [],
            "failed_attempts": 0,
            "locked_until": None,
            "mfa_enrolled_at": now,
        })
    await db.accounts.insert_many(accounts)

    patients = [
        {
            "id": "RPS-1030", "name": "Adaobi Eze", "sex": "Female", "dob": "1992-04-12",
            "phone": "0803-111-0001", "email": "adaobi@example.com", "address": "Lagos",
            "bloodGroup": "O+", "heightCm": 165, "weightKg": 62,
            "allergies": [], "conditions": [], "medications": [], "pastSurgeries": [],
            "familyHistory": "", "lifestyle": {"smoking": "Never", "alcohol": "Occasional"},
            "timeline": [{"id": 1, "date": "2026-09-01", "type": "Registered", "title": "Registered", "by": "Front desk"}],
            "allergiesRecorded": True,
        },
        {
            "id": "RPS-1033", "name": "Chinedu Okeke", "sex": "Male", "dob": "1988-11-03",
            "phone": "0803-111-0002", "email": "chinedu@example.com", "address": "Abuja",
            "bloodGroup": "A+", "heightCm": 178, "weightKg": 82,
            "allergies": [{"id": 1, "name": "Penicillin", "reaction": "Rash", "severity": "Moderate", "noted": "2026-09-10"}],
            "conditions": [{"id": 1, "name": "Hypertension", "since": "2020", "status": "Controlled"}],
            "medications": [], "pastSurgeries": [], "familyHistory": "",
            "lifestyle": {"smoking": "Former", "alcohol": "Social"},
            "timeline": [], "allergiesRecorded": True,
        },
        {
            "id": "RPS-1036", "name": "Chiamaka Obi", "sex": "Female", "dob": "1995-07-22",
            "phone": "0803-111-0003", "email": "chiamaka@example.com", "address": "Port Harcourt",
            "bloodGroup": "B+", "heightCm": 166, "weightKg": 68,
            "allergies": [], "conditions": [
                {"id": 1, "name": "Mild asthma", "since": "2008", "status": "Controlled"},
            ],
            "medications": [{"id": 1, "name": "Salbutamol inhaler", "dose": "As needed"}],
            "pastSurgeries": [{"id": 1, "name": "Appendectomy", "year": "2011", "note": "No complications"}],
            "familyHistory": "Mother: hypertension. Father: type 2 diabetes.",
            "lifestyle": {"smoking": "Never", "alcohol": "Occasional"},
            "timeline": [
                {"id": 1, "date": "2026-10-02", "type": "Registered", "title": "Registered at the centre", "by": "Front desk"},
                {"id": 2, "date": "2026-10-05", "type": "Consultation", "title": "Initial rhinoplasty consultation", "by": "Dr. Amadi"},
            ],
            "allergiesRecorded": True,
        },
        {
            "id": "RPS-1042", "name": "Ifeanyi Nwosu", "sex": "Male", "dob": "1990-01-15",
            "phone": "0803-111-0004", "email": "ifeanyi@example.com", "address": "Enugu",
            "bloodGroup": "O-", "heightCm": 175, "weightKg": 74,
            "allergies": [], "conditions": [], "medications": [], "pastSurgeries": [],
            "familyHistory": "", "lifestyle": {"smoking": "Never", "alcohol": "Never"},
            "timeline": [], "allergiesRecorded": True,
        },
    ]
    await db.patients.insert_many(patients)

    # A few appointments relative to today
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    appts = [
        {"id": "A-1", "patientId": "RPS-1033", "patient": "Chinedu Okeke", "type": "Follow-up",
         "clinicianId": "ST-02", "date": (monday).isoformat(), "start": "09:00", "duration": 30, "status": "Confirmed", "notes": ""},
        {"id": "A-2", "patientId": "RPS-1036", "patient": "Chiamaka Obi", "type": "Consultation",
         "clinicianId": "ST-01", "date": (monday + timedelta(days=1)).isoformat(), "start": "11:00", "duration": 45, "status": "Confirmed", "notes": ""},
        {"id": "A-3", "patientId": "RPS-1030", "patient": "Adaobi Eze", "type": "Consultation",
         "clinicianId": "ST-02", "date": (monday + timedelta(days=2)).isoformat(), "start": "10:00", "duration": 45, "status": "Confirmed", "notes": ""},
    ]
    await db.appointments.insert_many(appts)

    print("Seed complete.")
    print("Demo logins (password for all: Password1!):")
    print("  director@regal.example  (Medical Director)")
    print("  amadi@regal.example     (Surgeon)")
    print("  joy@regal.example       (Nurse / aftercare head)")
    print("  adaeze@regal.example    (Pharmacist)")
    print("  amina@regal.example     (Front desk)")
    print("  tunde@regal.example     (Finance)")
    print("  funke@regal.example     (HR)")
    print("  emeka@regal.example     (Lab nurse)")
    print()
    print("MFA secret for all demo accounts (add to authenticator app): JBSWY3DPEHPK3PXP")
    print("Or use a TOTP generator with that secret.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
