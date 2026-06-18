
from fastapi import APIRouter
router = APIRouter(prefix="/api/subscription")
@router.get("/health")
def health(): return {"status":"ok"}
