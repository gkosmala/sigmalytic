
from fastapi import APIRouter
router = APIRouter(prefix="/api/metrics")
@router.get("/health")
def health(): return {"status":"ok"}

