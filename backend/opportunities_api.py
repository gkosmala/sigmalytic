from fastapi import APIRouter
router=APIRouter(prefix='/api/v2/opportunities')
@router.get('')
def opportunities(): return []

