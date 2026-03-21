LEAD_SEARCH_OPERATORS = [
    {"code": "eq", "label": "Igual (=)"},
    {"code": "neq", "label": "No igual (!=)"},
    {"code": "gt", "label": "Mayor que (>)"},
    {"code": "lt", "label": "Menor que (<)"},
    {"code": "gte", "label": "Mayor o igual (>=)"},
    {"code": "lte", "label": "Menor o igual (<=)"},
    {"code": "like", "label": "Contiene (texto)"},
    {"code": "ilike", "label": "Contiene (texto, ignora mayusculas)"},
    {"code": "in", "label": "Lista de opciones"},
    {"code": "between", "label": "Entres dos valores (rangos)"}
]

LEAD_ROUTING_RULE_CONDITION_TYPES = [
    {"code": "NOMENCLATOR", "label": "Valor de Nomenclador"},
    {"code": "CUSTOM_FIELD", "label": "Campo Personalizado"}
]

TEAM_ROLES = [
    {"code": "MANAGER", "label": "Mánager de Equipo"},
    {"code": "AGENT", "label": "Agente de Ventas"}
]

LEAD_STATE_CATEGORIES = [
    {"code": "OPEN", "label": "Abierto"},
    {"code": "WON", "label": "Ganado"},
    {"code": "LOST", "label": "Perdido"}
]


SYSTEM_DICTIONARIES = {
    "lead_search_operators": LEAD_SEARCH_OPERATORS,
    "routing_condition_types": LEAD_ROUTING_RULE_CONDITION_TYPES,
    "team_roles": TEAM_ROLES,
    "lead_states_categories": LEAD_STATE_CATEGORIES
}
    


