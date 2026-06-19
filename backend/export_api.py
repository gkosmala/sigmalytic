
from fastapi import APIRouter
router = APIRouter(prefix="/api/export")
@router.get("/health")
def health(): return {"status":"ok"}

