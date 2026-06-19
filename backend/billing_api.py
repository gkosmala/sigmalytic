
from fastapi import APIRouter
router = APIRouter(prefix="/api/billing")

@router.get("/health")
def health():
    return {"status":"ok"}

