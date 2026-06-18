
from fastapi import APIRouter
router = APIRouter(prefix="/api/admin")

@router.get("/health")
def health():
    return {"status":"ok"}
