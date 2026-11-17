from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.mongodb_db]
    # Create indexes
    await _db.staff.create_index("email", unique=True)
    await _db.staff.create_index("staffId", unique=True)
    await _db.accounts.create_index("staffId", unique=True)
    await _db.patients.create_index("id", unique=True)
    await _db.sessions.create_index("session_id", unique=True)
    await _db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await _db.audit_log.create_index([("at", -1)])


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db
