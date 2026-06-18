
from fastapi import APIRouter
router = APIRouter(prefix="/api/watchlist")

@router.get("/health")
def health():
    return {"status":"ok"}
