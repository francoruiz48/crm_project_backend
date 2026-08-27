from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Depends
from app.core.security import get_current_user_roles
from app.core.dictionaries import SYSTEM_DICTIONARIES, get_entity_delete_strategies

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
    # "entity_delete_strategies" se calcula en cada request (no es parte del dict
    # estático de SYSTEM_DICTIONARIES) para que siempre refleje el delete_strategy
    # real configurado en cada repositorio -- ver get_entity_delete_strategies().
    dictionaries = {**SYSTEM_DICTIONARIES, "entity_delete_strategies": get_entity_delete_strategies()}

    if not keys:
        return dictionaries

    # Convertimos el string "keys1,key2" en una lista ["keys1", "key2"]
    requested_keys = [k.strip() for k in keys.split(",")]

    # Filtramos el diccionario para devolver solo lo que pidieron
    response = {
        key: dictionaries[key]
        for key in requested_keys
        if key in dictionaries
    }

    return response