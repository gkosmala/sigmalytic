
from fastapi import APIRouter
router = APIRouter(prefix="/api/notification")
@router.get("/health")
def health(): return {"status":"ok"}

