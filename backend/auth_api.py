
from fastapi import APIRouter
router = APIRouter(prefix="/api/auth")

@router.get("/health")
def health():
    return {"status":"ok"}

