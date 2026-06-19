
from fastapi import APIRouter
router = APIRouter(prefix="/api/alerts")

@router.get("/health")
def health():
    return {"status":"ok"}

