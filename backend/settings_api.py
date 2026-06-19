
from fastapi import APIRouter
router = APIRouter(prefix="/api/settings")
@router.get("/health")
def health(): return {"status":"ok"}

