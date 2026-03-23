from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.search_service import SearchService
from app.schemas.search_schema import GlobalSearchResponse
from app.core.security import get_current_user_roles

router = APIRouter()

@router.get("/search", response_model=GlobalSearchResponse)
def search_global(
    query: str = Query(..., min_length=3, description="Término de búsqueda"),
    db: Session = Depends(get_db),
    user_context = Depends(get_current_user_roles)
):
    return SearchService.global_search(db, query=query, user_context=user_context)