from fastapi import APIRouter
router=APIRouter(prefix='/api/v2/research-detail')
@router.get('/{symbol}')
def detail(symbol:str): return {'symbol':symbol}

