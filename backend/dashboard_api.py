from fastapi import APIRouter
router=APIRouter(prefix='/api/v2/dashboard')
@router.get('')
def dashboard(): return {}

