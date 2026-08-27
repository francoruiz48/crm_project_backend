from app.core.constans import SystemAuditLogAction


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
    {"code": "NATIVE", "label": "Campo Nativo del Lead"},
    {"code": "DYNAMIC", "label": "Campo Personalizado (Dinámico)"}
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

SYSTEM_ENTITIES_REGISTRY = {
    # --- ENTIDADES CON CRUD COMPLETO ---
    "lead": {"model": "Lead", "name": "Lead", "crud_type": "FULL"},
    "lead_field": {"model": "LeadField", "name": "Campo Personalizado", "crud_type": "FULL"},
    "validation_rule": {"model": "ValidationRule", "name": "Regla de Validación", "crud_type": "FULL"},
    "campaign": {"model": "Campaign", "name": "Campaña", "crud_type": "FULL"},
    "nomenclator": {"model": "Nomenclator", "name": "Nomenclador", "crud_type": "FULL"},
    "nomenclator_item": {"model": "NomenclatorItem", "name": "Ítem de Nomenclador", "crud_type": "FULL"},
    "user": {"model": "User", "name": "Usuario", "crud_type": "FULL"},
    "role": {"model": "Role", "name": "Rol", "crud_type": "FULL"},
    "workspace": {"model": "Workspace", "name": "Espacio de Trabajo", "crud_type": "FULL"},
    "lead_field_section": {"model": "LeadFieldSection", "name": "Sección de Campo", "crud_type": "FULL"},
    "lead_comment": {"model": "LeadComment", "name": "Comentario de Lead", "crud_type": "FULL"},
    "organization": {"model": "Organization", "name": "Organización", "crud_type": "FULL"},
    "lead_flow": {"model": "LeadFlow", "name": "Ciclo de Vida", "crud_type": "FULL"},
    "lead_state": {"model": "LeadState", "name": "Etapa de Ciclo de Vida", "crud_type": "FULL"},
    "lead_state_transition": {"model": "LeadStateTransition", "name": "Transición de Etapa", "crud_type": "FULL"},
    "team": {"model": "Team", "name": "Equipo", "crud_type": "FULL"},
    "team_member": {"model": "TeamMember", "name": "Miembro de Equipo", "crud_type": "FULL"},
    "team_workspace_access": {"model": "TeamWorkspaceAccess", "name": "Acceso a Espacio", "crud_type": "FULL"},
    "team_campaign_access": {"model": "TeamCampaignAccess", "name": "Acceso a Campaña", "crud_type": "FULL"},
    "lead_routing_policy": {"model": "LeadRoutingPolicy", "name": "Política de Enrutamiento", "crud_type": "FULL"},
    "lead_view": {"model": "LeadView", "name": "Vista de Lead", "crud_type": "FULL"},
    "web_form": {"model": "WebForm", "name": "Formulario Web", "crud_type": "FULL"},
    "field_automation": {"model": "FieldAutomation", "name": "Automatización de Campo", "crud_type": "FULL"},
    "tag": {"model": "Tag", "name": "Etiqueta", "crud_type": "FULL"},
    # Hallazgo #27 (2026-07-11): faltaba en el registro — sin esta entrada no
    # existe ningún permiso lead_contact_state:*, y ningún usuario no-superadmin
    # puede usar /lead_contact_states/*, ni siquiera el admin de la organización.
    "lead_contact_state": {"model": "LeadContactState", "name": "Estado", "crud_type": "FULL"},

    # --- ENTIDADES DE SOLO LECTURA (Catálogos y Logs) ---
    "lead_field_type": {"model": "LeadFieldType", "name": "Tipo de Campo", "crud_type": "READ_ONLY"},
    "lead_field_subtype": {"model": "LeadFieldSubtype", "name": "Subtipo de Campo", "crud_type": "READ_ONLY"},
    "permission": {"model": "Permission", "name": "Permiso", "crud_type": "READ_ONLY"},
    "lead_state_history": {"model": "LeadStateHistory", "name": "Historial de Etapa", "crud_type": "READ_ONLY"},
    "system_audit_log": {"model": "SystemAuditLog", "name": "Registro de Auditoría", "crud_type": "READ_ONLY"},
    "lead_activity_history": {"model": "LeadActivityHistory", "name": "Historial de Actividad", "crud_type": "READ_ONLY"}
}

#Entidades para el Front
ENTITIES = {
    registry["model"]: registry["name"] 
    for code, registry in SYSTEM_ENTITIES_REGISTRY.items()
}

SYSTEM_AUDIT_LOG_ACTIONS = {
    SystemAuditLogAction.CREATED: "Creación",
    SystemAuditLogAction.UPDATED: "Actualización",
    SystemAuditLogAction.DELETED: "Eliminación",
    SystemAuditLogAction.DISABLED: "Desactivación",
    SystemAuditLogAction.ACTIVATED: "Activación",
    SystemAuditLogAction.PATCHED: "Modificación Parcial",
    SystemAuditLogAction.PROMOTE_SUPERUSER: "Promoción a SuperAdmin",
    SystemAuditLogAction.PROMOTE_OWNER: "Promoción a Owner"
}

AUTOMATION_COMPATIBILITY_MATRIX = {
    "STRING": {
        "operators": ["EQUALS", "NOT_EQUALS", "CONTAINS", "NOT_CONTAINS", "STARTS_WITH", "ENDS_WITH", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "NORMALIZE_TEXT", "CONCAT_FIELDS"]
    },
    "INT": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "INCREMENT", "DECREMENT"]
    },
    "NUMBER": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD"]
    },
    "BOOL": {
        "operators": ["EQUALS", "NOT_EQUALS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD"]
    },
    "DATE": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_PAST", "IS_FUTURE", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "SET_CURRENT_DATE", "SET_DATE_OFFSET"]
    },
    "DATE_TIME": {
        "operators": ["EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN", "IS_PAST", "IS_FUTURE", "STARTS_WITH", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "SET_CURRENT_DATETIME"]
    },
    "SELECTOR": {
        "operators": ["EQUALS", "NOT_EQUALS", "CONTAINS", "NOT_CONTAINS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "APPEND_TO_LIST", "REMOVE_FROM_LIST"]
    },
    "LEAD": {
        "operators": ["CONTAINS", "NOT_CONTAINS", "IS_EMPTY", "IS_NOT_EMPTY"],
        "actions": ["SET_VALUE", "SET_VALUE_IF_EMPTY", "CLEAR_VALUE", "COPY_FROM_FIELD", "APPEND_TO_LIST", "REMOVE_FROM_LIST"]
    }
}

SYSTEM_DICTIONARIES = {
    "lead_search_operators": LEAD_SEARCH_OPERATORS,
    "routing_condition_types": LEAD_ROUTING_RULE_CONDITION_TYPES,
    "team_roles": TEAM_ROLES,
    "lead_states_categories": LEAD_STATE_CATEGORIES,    "lead_view_visibilities": LEAD_VIEW_VISIBILITIES,
    "automation_compatibility_matrix": AUTOMATION_COMPATIBILITY_MATRIX,
    "entities": ENTITIES,
    "system_audit_log_actions": SYSTEM_AUDIT_LOG_ACTIONS
}


def get_entity_delete_strategies() -> dict:
    """
    Devuelve dinámicamente {NombreDelModelo: delete_strategy} para cada repositorio
    del sistema (ej: {"Lead": "HARD_DELETE_ALWAYS", "Role": "SOFT_DELETE_ALWAYS", ...}).

    A diferencia del resto de SYSTEM_DICTIONARIES, esto NO es un dict estático: se
    recorren en runtime todas las subclases de BaseRepository (recursivo, por si algún
    repo hereda de otro repo en vez de BaseRepository directamente) y se lee el
    atributo real `delete_strategy` de cada una. Así, si mañana cambia la estrategia
    de un repo o se agrega uno nuevo, se refleja solo acá sin tocar este archivo.

    Import local (no a nivel de módulo) a propósito: BaseRepository importa
    app.core.security / app.core.context, y este módulo (core/dictionaries.py) lo
    importan tanto app/db/init_data.py como app/controllers/meta_data_controller.py
    en distintos puntos del arranque -- traerlo a nivel de módulo arriesga un ciclo
    de imports. Es seguro llamarlo desde acá porque quien lo invoca (el endpoint
    /metadata/dictionaries) solo corre en tiempo de request, momento en el que
    app/routers/__init__.py ya importó todos los controllers (y por lo tanto todos
    los repositorios) al arrancar la app.
    """
    from app.db.repository.base_repository import BaseRepository

    def _all_subclasses(cls):
        result = set()
        for sub in cls.__subclasses__():
            result.add(sub)
            result.update(_all_subclasses(sub))
        return result

    strategies = {}
    for repo_cls in _all_subclasses(BaseRepository):
        model = getattr(repo_cls, "model", None)
        if model is None:
            continue
        strategies[model.__name__] = repo_cls.delete_strategy
    return strategies
    



