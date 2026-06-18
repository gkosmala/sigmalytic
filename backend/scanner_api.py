
from fastapi import APIRouter
router = APIRouter(prefix="/api/scanner")

@router.get("/health")
def health():
    return {"status":"ok"}
