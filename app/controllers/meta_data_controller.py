from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Depends
from app.core.security import get_current_user_roles
from app.core.dictionaries import SYSTEM_DICTIONARIES

router = APIRouter(prefix="/metadata", tags=["Metadata & Dictionaries"])

@router.get("/dictionaries", response_model=Dict[str, Any])
def get_dictionaries(
    # Permite al frontend pedir solo lo que necesita separando por comas
    # Ejemplo: ?keys=team_roles,routing_condition_types
    keys: Optional[str] = Query(None, description="Claves separadas por coma. Si se omite, trae todos."),
    user_context = Depends(get_current_user_roles)
):
    """
    Devuelve los listados estáticos necesarios para poblar selects y dropdowns en el Frontend.
    """
    if not keys:
        return SYSTEM_DICTIONARIES

    # Convertimos el string "keys1,key2" en una lista ["keys1", "key2"]
    requested_keys = [k.strip() for k in keys.split(",")]
    
    # Filtramos el diccionario para devolver solo lo que pidieron
    response = {
        key: SYSTEM_DICTIONARIES[key] 
        for key in requested_keys 
        if key in SYSTEM_DICTIONARIES
    }
    
    return response