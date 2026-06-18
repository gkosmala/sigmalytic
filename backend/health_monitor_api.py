from fastapi import APIRouter
router=APIRouter(prefix='/api/v2/system')
@router.get('/health')
def health(): return {'status':'healthy'}
