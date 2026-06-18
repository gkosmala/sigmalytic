
from fastapi import APIRouter
router = APIRouter(prefix="/api/audit")
@router.get("/health")
def health(): return {"status":"ok"}
