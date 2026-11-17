from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.database import connect_db, close_db
from app.config import get_settings
from app.routers import auth, staff, patients, dashboard, appointments, lab

# Additional routers can be imported as they are completed
# from app.routers import consultations, surgeries, aftercare, pharmacy, billing, tasks, messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="Regal HMS API",
    description="Backend for Regal Plastic Surgery Centre Hospital Management System",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Ensure error body shape for the frontend
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "message" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(status_code=exc.status_code, content={"message": str(detail)})
    return JSONResponse(status_code=500, content={"message": "Internal server error."})


# Mount routers under /api
app.include_router(auth.router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(lab.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "regal-hms-backend"}


@app.get("/")
async def root():
    return {"message": "Regal HMS API. See /docs for OpenAPI."}
