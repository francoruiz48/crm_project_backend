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

LEAD_VIEW_VISIBILITIES = [
    {"code": "PRIVATE", "label": "Privada"},
    {"code": "TEAM", "label": "Equipo"},
    {"code": "PUBLIC", "label": "Pública"}
]

AUTOMATION_COMPATIBILITY_MATRIX = {
    "STRING": {
        "operators": ["EQUALS", "NOT_EQUALS", "CONTAINS", "NOT_CONTAINS", "STARTS_WITH", "ENDS_WITH", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD"]
    },
    "INT": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD", "INCREMENT", "DECREMENT"]
    },
    "NUMBER": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD"]
    },
    "BOOL": {
        "operators": ["EQUALS", "NOT_EQUALS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD"]
    },
    "DATE": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_PAST", "IS_FUTURE", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD", "SET_CURRENT_DATE"]
    },
    "DATE_TIME": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_PAST", "IS_FUTURE", "STARTS_WITH", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD", "SET_CURRENT_DATETIME"]
    },
    "SELECTOR": {
        "operators": ["EQUALS", "NOT_EQUALS", "CONTAINS", "NOT_CONTAINS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD", "APPEND_TO_LIST", "REMOVE_FROM_LIST"]
    },
    "LEAD": {
        "operators": ["CONTAINS", "NOT_CONTAINS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "CLEAR_VALUE", "COPY_FROM_FIELD", "APPEND_TO_LIST", "REMOVE_FROM_LIST"]
    }
}

SYSTEM_DICTIONARIES = {
    "lead_search_operators": LEAD_SEARCH_OPERATORS,
    "routing_condition_types": LEAD_ROUTING_RULE_CONDITION_TYPES,
    "team_roles": TEAM_ROLES,
    "lead_states_categories": LEAD_STATE_CATEGORIES,
    "lead_view_visibilities": LEAD_VIEW_VISIBILITIES,
    "automation_compatibility_matrix": AUTOMATION_COMPATIBILITY_MATRIX
}
    



