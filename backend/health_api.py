
from fastapi import APIRouter
router = APIRouter(prefix="/api/health")
@router.get("/health")
def health(): return {"status":"ok"}
