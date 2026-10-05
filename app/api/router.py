from fastapi import APIRouter
from app.api.v1.institutions import router as institutions_router
from app.api.v1.ratings import router as ratings_router
from app.api.v1.collector import router as collector_router
from app.api.v1.excel import router as excel_router
from app.api.v1.logs import router as logs_router

api_router = APIRouter()

api_router.include_router(institutions_router)
api_router.include_router(ratings_router)
api_router.include_router(collector_router)
api_router.include_router(excel_router)
api_router.include_router(logs_router)
