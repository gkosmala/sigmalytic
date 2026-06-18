
from fastapi import APIRouter
router = APIRouter(prefix="/api/reports")

@router.get("/health")
def health():
    return {"status":"ok"}
