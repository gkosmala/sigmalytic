
from fastapi import APIRouter
router = APIRouter(prefix="/api/search")
@router.get("/health")
def health(): return {"status":"ok"}
