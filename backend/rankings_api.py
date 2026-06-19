from fastapi import APIRouter
router=APIRouter(prefix='/api/v2/rankings')
@router.get('')
def rankings(): return []

