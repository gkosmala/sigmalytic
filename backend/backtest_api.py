
from fastapi import APIRouter
router = APIRouter(prefix="/api/backtest")

@router.get("/health")
def health():
    return {"status":"ok"}
