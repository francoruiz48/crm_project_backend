from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.search_service import SearchService
from app.schemas.search_schema import GlobalSearchResponse
from app.core.security import get_current_user

router = APIRouter()

@router.get("/search", response_model=GlobalSearchResponse)
def search_global(
    query: str = Query(..., min_length=3, description="Término de búsqueda"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return SearchService.global_search(db, query=query)