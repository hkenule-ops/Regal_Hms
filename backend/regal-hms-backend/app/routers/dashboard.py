from fastapi import APIRouter, Depends
from datetime import date
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.permissions import can
from app.core.security import iso_now

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    db = get_db()
    today = iso_now()[:10]

    # Counts
    patients_count = await db.patients.count_documents({})
    appts_today = await db.appointments.count_documents({"date": today, "status": {"$ne": "Cancelled"}})
    surgeries_today = await db.surgeries.count_documents({"date": today, "status": {"$nin": ["Cancelled", "Completed"]}})
    open_tasks = await db.tasks.count_documents({
        "$or": [
            {"assigneeId": user["staffId"], "status": {"$in": ["Open", "In progress"]}},
            {"department": user.get("department"), "assigneeId": None, "status": {"$in": ["Open", "In progress"]}},
        ]
    })

    kpis = [
        {"key": "patients", "label": "Patients", "value": patients_count},
        {"key": "appointments", "label": "Today's appointments", "value": appts_today},
        {"key": "theatre", "label": "Theatre today", "value": surgeries_today},
        {"key": "tasks", "label": "My open tasks", "value": open_tasks},
    ]

    # Revenue only for director / finance
    revenue = None
    if can(user, "billing.money"):
        # Simple sum of paid invoices in last 30 days (placeholder)
        pipeline = [
            {"$match": {"status": {"$in": ["Paid", "Part-paid"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]
        agg = await db.invoices.aggregate(pipeline).to_list(1)
        revenue = {
            "total": agg[0]["total"] if agg else 0,
            "currency": "NGN",
            "period": "all time (demo)",
        }

    # Alerts (role-filtered)
    alerts = []
    if can(user, "billing.money"):
        overdue = await db.invoices.count_documents({"status": "Overdue"})
        if overdue:
            alerts.append({
                "id": "overdue-inv",
                "type": "money",
                "message": f"{overdue} overdue invoice(s)",
                "roles": ["director", "finance", "frontdesk"],
            })

    # Today's theatre list
    theatre = []
    cursor = db.surgeries.find({"date": today, "status": {"$nin": ["Cancelled"]}}).sort("start", 1)
    async for s in cursor:
        theatre.append({
            "id": s.get("id"),
            "time": s.get("start"),
            "patient": s.get("patient"),
            "procedure": s.get("procedure"),
            "theatre": s.get("theatreName") or s.get("theatreId"),
            "surgeon": s.get("surgeonName") or s.get("surgeonId"),
            "status": "In progress" if s.get("status") == "In theatre" else s.get("status"),
        })

    return {
        "kpis": kpis,
        "revenue": revenue,
        "alerts": [a for a in alerts if user["role"] in a.get("roles", [])],
        "theatreToday": theatre,
        "user": user,
    }


@router.get("/badges")
async def badges(user: dict = Depends(get_current_user)):
    db = get_db()
    # Messages unread
    threads = await db.message_threads.find({
        "memberIds": user["staffId"],
        "unreadBy": user["staffId"],
    }).to_list(100)
    msg_count = len(threads)

    # Tasks
    task_count = await db.tasks.count_documents({
        "$or": [
            {"assigneeId": user["staffId"], "status": {"$in": ["Open", "In progress"]}},
            {"department": user.get("department"), "assigneeId": None, "status": {"$in": ["Open", "In progress"]}},
        ]
    })

    # Pharmacy (prescriptions sent to me)
    pharm = 0
    if user["role"] in ("pharmacist", "surgeon", "nurse", "director"):
        pharm = await db.prescriptions.count_documents({
            "sentToId": user["staffId"],
            "reply": None,
            "status": {"$nin": ["Cancelled", "Dispensed"]},
        })

    # Laboratory queue
    lab = 0
    if user.get("department") == "laboratory" or (user["role"] == "nurse" and user.get("department") == "laboratory"):
        lab = await db.lab_requests.count_documents({
            "status": {"$in": ["Requested", "Collected"]},
            "$or": [
                {"takenById": {"$in": [None, ""]}},
                {"takenById": user["staffId"]},
            ],
        })

    return {
        "messages": msg_count,
        "tasks": task_count,
        "pharmacy": pharm,
        "laboratory": lab,
    }
