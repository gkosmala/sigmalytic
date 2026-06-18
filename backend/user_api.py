
from fastapi import APIRouter
router = APIRouter(prefix="/api/user")
@router.get("/health")
def health(): return {"status":"ok"}
