"""
seed_data.py  –  Script de datos de prueba realistas para el CRM
=================================================================
Ejecutar DESPUÉS de que la app esté corriendo (init_data.py ya habrá
inicializado tipos, subtypes, secciones, nomencladores globales y RBAC).

Uso:
    python seed_data.py

Requiere:
    pip install requests faker
"""

import requests
import random
import time
import os
from datetime import datetime, timedelta, date
from faker import Faker

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
BASE_URL      = "http://localhost:8000"
SEED_EMAIL    = "francoruiz.admin@crm.com"
SEED_PASSWORD = "ADQSilR4aAKCO%a^"
SEED_USER_PASSWORD = "Semilla2026Crm"  # contraseña de los usuarios seed (invite+register)
LOCALE        = "es_AR"
fake          = Faker(LOCALE)

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

# Límite de warnings de CALCULATED para no saturar consola
_calc_warnings = []
MAX_CALC_WARNINGS = 10


# ---------------------------------------------------------------------------
# HELPERS DE LOGGING
# ---------------------------------------------------------------------------
def log(msg: str, level: str = "OK", indent: int = 0):
    icons = {"OK": "✅", "ERR": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ ", "STEP": "🔷"}
    prefix = " " * indent + icons.get(level, "•")
    print(f"{prefix} {msg}")

def warn_calculated(field_name: str, expected, got):
    """Emite un warning de campo CALCULATED, máximo MAX_CALC_WARNINGS veces."""
    if len(_calc_warnings) >= MAX_CALC_WARNINGS:
        return
    _calc_warnings.append(field_name)
    log(f"CALCULATED '{field_name}': esperado≈{expected}, obtenido={got}", "WARN", indent=6)
    if len(_calc_warnings) == MAX_CALC_WARNINGS:
        log("(Se alcanzó el límite de warnings de CALCULATED, no se emitirán más)", "WARN", indent=6)


# ---------------------------------------------------------------------------
# AUTENTICACIÓN
# ---------------------------------------------------------------------------
def login(email: str = SEED_EMAIL, password: str = SEED_PASSWORD):
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    if r.status_code != 200:
        log(f"Login fallido ({r.status_code}): {r.text}", "ERR")
        raise SystemExit(1)
    token = r.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    log(f"Autenticado como {email}", "OK")


# ---------------------------------------------------------------------------
# HELPERS DE SESIÓN / TENANT
# ---------------------------------------------------------------------------
def set_tenant(org_id: int):
    session.headers.update({"X-Organization-Id": str(org_id)})

def api_get(path: str, params: dict = None):
    r = session.get(f"{BASE_URL}{path}", params=params)
    return r

def api_post(path: str, payload: dict):
    r = session.post(f"{BASE_URL}{path}", json=payload)
    return r

def api_put(path: str, payload: dict):
    r = session.put(f"{BASE_URL}{path}", json=payload)
    return r

def api_delete(path: str):
    r = session.delete(f"{BASE_URL}{path}")
    return r


# ---------------------------------------------------------------------------
# HELPERS: NOMENCLADORES GLOBALES
# ---------------------------------------------------------------------------
_nom_cache: dict[str, tuple[list, int]] = {}   # name -> (items, id)

def get_global_nomenclator(name: str) -> tuple[list, int | None]:
    """
    Busca un nomenclador GLOBAL (organization_id=NULL) por nombre.
    Usa caché para no repetir llamadas.
    """
    if name in _nom_cache:
        return _nom_cache[name]

    r = api_get("/nomenclators", params={"search": name, "search_fields": "name", "page_size": 50})
    if r.status_code != 200:
        log(f"Error buscando nomenclador global '{name}': {r.text}", "ERR")
        return [], None

    items_list = r.json().get("items", [])
    if not items_list:
        log(f"Nomenclador global '{name}' no encontrado", "WARN")
        return [], None

    nom = items_list[0]
    nom_id = nom["id"]

    # Traer ítems
    r2 = api_get("/nomenclator_items", params={"nomenclator_id": nom_id, "page_size": 500})
    opts = r2.json().get("items", []) if r2.status_code == 200 else []
    _nom_cache[name] = (opts, nom_id)
    return opts, nom_id

def get_or_create_org_nomenclator(name: str, options: list[str]) -> tuple[list, int | None]:
    """
    Busca o crea un nomenclador propio de la organización (sin campaign_id).
    """
    cache_key = f"org::{name}"
    if cache_key in _nom_cache:
        return _nom_cache[cache_key]

    r = api_get("/nomenclators", params={"search": name, "global_nomenclator": "false", "page_size": 50})
    existing = r.json().get("items", []) if r.status_code == 200 else []

    # Filtrar por nombre exacto
    match = next((n for n in existing if n["name"].lower() == name.lower()), None)
    if match:
        nom_id = match["id"]
    else:
        cr = api_post("/nomenclators/", {"name": name})
        if cr.status_code not in (200, 201):
            log(f"Error creando nomenclador '{name}': {cr.text}", "ERR")
            return [], None
        nom_id = cr.json()["id"]
        for opt in options:
            api_post("/nomenclator_items/", {"nomenclator_id": nom_id, "value": opt, "active": True})

    r2 = api_get("/nomenclator_items", params={"nomenclator_id": nom_id, "page_size": 500})
    opts = r2.json().get("items", []) if r2.status_code == 200 else []
    _nom_cache[cache_key] = (opts, nom_id)
    return opts, nom_id

def get_or_create_campaign_nomenclator(name: str, options: list[str], campaign_id: int) -> tuple[list, int | None]:
    """
    Nomenclador específico de una campaña.
    """
    cache_key = f"camp{campaign_id}::{name}"
    if cache_key in _nom_cache:
        return _nom_cache[cache_key]

    r = api_get("/nomenclators", params={"search": name, "campaign_id": campaign_id, "page_size": 50})
    existing = r.json().get("items", []) if r.status_code == 200 else []
    match = next((n for n in existing if n["name"].lower() == name.lower()), None)

    if match:
        nom_id = match["id"]
    else:
        cr = api_post("/nomenclators/", {"name": name, "campaign_id": campaign_id})
        if cr.status_code not in (200, 201):
            log(f"Error creando nomenclador de campaña '{name}': {cr.text}", "ERR")
            return [], None
        nom_id = cr.json()["id"]
        for opt in options:
            api_post("/nomenclator_items/", {"nomenclator_id": nom_id, "value": opt, "active": True})

    r2 = api_get("/nomenclator_items", params={"nomenclator_id": nom_id, "page_size": 500})
    opts = r2.json().get("items", []) if r2.status_code == 200 else []
    _nom_cache[cache_key] = (opts, nom_id)
    return opts, nom_id

def rand_nom_id(items: list) -> int | None:
    if not items:
        return None
    return random.choice(items)["id"]

def rand_nom_ids(items: list, max_k: int = 3) -> list[int]:
    if not items:
        return []
    k = random.randint(1, min(max_k, len(items)))
    return [i["id"] for i in random.sample(items, k)]


# ---------------------------------------------------------------------------
# HELPERS: SECCIONES
# ---------------------------------------------------------------------------
_section_cache: dict[str, int] = {}

def get_or_create_section(name: str) -> int:
    if name in _section_cache:
        return _section_cache[name]
    r = api_get("/lead_field_sections", params={"search": name, "page_size": 20})
    items = r.json().get("items", []) if r.status_code == 200 else []
    match = next((s for s in items if s["name"].lower() == name.lower()), None)
    if match:
        sec_id = match["id"]
    else:
        cr = api_post("/lead_field_sections/", {"name": name})
        sec_id = cr.json()["id"] if cr.status_code in (200, 201) else 1
    _section_cache[name] = sec_id
    return sec_id


# ---------------------------------------------------------------------------
# HELPERS: ORGANIZACIONES, WORKSPACES, CAMPAÑAS
# ---------------------------------------------------------------------------
def create_organization(name: str, description: str = None) -> int | None:
    r = api_post("/organizations/", {"name": name, "description": description})
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando organización '{name}': {r.text}", "ERR")
    return None

def create_workspace(name: str, description: str = None) -> int | None:
    r = api_post("/workspaces/", {"name": name, "description": description})
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando workspace '{name}': {r.text}", "ERR")
    return None

def create_campaign(name: str, workspace_id: int, lead_flow_id: int = None, is_public: bool = True) -> int | None:
    payload = {"name": name, "workspace_id": workspace_id, "active": True, "is_public": is_public}
    if lead_flow_id:
        payload["lead_flow_id"] = lead_flow_id
    r = api_post("/campaigns/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando campaña '{name}': {r.text}", "ERR")
    return None

def get_default_flow(org_id: int) -> int | None:
    """Obtiene el lead_flow_id por defecto de la organización."""
    r = api_get("/lead_flows", params={"page_size": 10})
    if r.status_code == 200:
        items = r.json().get("items", [])
        if items:
            return items[-1]["id"]   # el más antiguo (el default que creó OrganizationService)
    return None

def get_flow_states(flow_id: int) -> list:
    """Retorna los estados de un flujo ordenados."""
    r = api_get("/lead_states", params={"lead_flow_id": flow_id, "page_size": 50})
    return r.json().get("items", []) if r.status_code == 200 else []

def get_flow_transitions(flow_id: int) -> list:
    # detailed=true: necesitamos from_state/to_state anidados con su public_uuid real (Fase 4,
    # ver AGENTS.md). Sin esto, from_state_id/to_state_id vienen como int interno crudo y
    # advance_lead_through_flow() los manda tal cual a change_state, que espera un public_uuid.
    r = api_get("/lead_state_transitions", params={"lead_flow_id": flow_id, "page_size": 200, "detailed": "true"})
    return r.json().get("items", []) if r.status_code == 200 else []


# ---------------------------------------------------------------------------
# HELPERS: FLUJO PERSONALIZADO
# ---------------------------------------------------------------------------
def create_custom_flow(name: str, states_def: list[dict], transitions_pairs: list[tuple]) -> int | None:
    """
    Crea un flujo con sus estados y transiciones.
    states_def: [{"name": ..., "category": "OPEN"|"WON"|"LOST", "is_initial": bool, "order": int|None}]
    transitions_pairs: [(from_idx, to_idx), ...]  – índices en states_def
    """
    r = api_post("/lead_flows/", {"name": name, "description": f"Flujo personalizado: {name}"})
    if r.status_code not in (200, 201):
        log(f"Error creando flujo '{name}': {r.text}", "ERR")
        return None
    flow_id = r.json()["id"]

    state_ids = []
    for sd in states_def:
        sr = api_post("/lead_states/", {
            "lead_flow_id": flow_id,
            "name": sd["name"],
            "category": sd.get("category", "OPEN"),
            "is_initial": sd.get("is_initial", False),
            "order": sd.get("order"),
            "color": sd.get("color"),
        })
        if sr.status_code in (200, 201):
            state_ids.append(sr.json()["id"])
        else:
            log(f"  Error creando estado '{sd['name']}': {sr.text}", "ERR")
            state_ids.append(None)

    # Transiciones en bulk
    pairs = []
    for from_idx, to_idx in transitions_pairs:
        if state_ids[from_idx] and state_ids[to_idx]:
            pairs.append({"from_state_id": state_ids[from_idx], "to_state_id": state_ids[to_idx]})

    if pairs:
        tr = api_post("/lead_state_transitions/bulk", {"lead_flow_id": flow_id, "transitions": pairs})
        if tr.status_code not in (200, 201):
            log(f"  Error creando transiciones bulk: {tr.text}", "WARN")

    return flow_id


# ---------------------------------------------------------------------------
# HELPERS: USUARIOS Y EQUIPOS
# ---------------------------------------------------------------------------
def get_org_members(org_id: int) -> list:
    """Lista los usuarios de una organización vía /users/in-org/members."""
    r = session.get(f"{BASE_URL}/users/in-org/members", headers={"X-Organization-Id": str(org_id)})
    return r.json() if r.status_code == 200 else []

def create_user(name: str, email: str, org_id: int, role_code: str = "agent") -> int | None:
    """
    Crea un usuario nuevo y lo une a la organización usando el flujo real:
    1. /auth/invite (como admin/superuser) genera un invite_token para ese email+rol.
    2. /auth/register (público, sin auth) crea la cuenta y, al incluir el
       invite_token, la une automáticamente a la organización con ese rol.
    Es idempotente: si el email ya existe, busca el usuario en la org y lo reusa.
    """
    first_name, _, last_name = name.partition(" ")
    last_name = last_name or first_name

    inv = api_post("/auth/invite", {"email": email, "organization_id": org_id, "role_code": role_code})
    if inv.status_code != 200:
        log(f"Error invitando a '{email}': {inv.text}", "ERR")
        return None
    invite_token = inv.json()["invite_token"]

    r = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "name": first_name, "last_name": last_name, "email": email,
            "password": SEED_USER_PASSWORD, "invite_token": invite_token,
        },
        headers={"Content-Type": "application/json"},
    )
    if r.status_code not in (200, 201):
        # Si ya existía la cuenta, la buscamos entre los miembros de la org (script idempotente)
        match = next((u for u in get_org_members(org_id) if u["email"] == email), None)
        if match:
            return match["id"]
        log(f"Error registrando usuario '{email}': {r.text}", "ERR")
        return None

    # /auth/register solo devuelve tokens, no el user id: lo buscamos en la org.
    match = next((u for u in get_org_members(org_id) if u["email"] == email), None)
    if not match:
        log(f"Usuario '{email}' registrado pero no encontrado en la org {org_id}", "WARN")
        return None
    return match["id"]

def create_team(name: str, visibility_shared: bool = True) -> int | None:
    r = api_post("/teams/", {"name": name, "is_visibility_shared": visibility_shared})
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando equipo '{name}': {r.text}", "ERR")
    return None

def add_team_member(team_id: int, user_id: int, role: str = "AGENT"):
    api_post("/team_members/", {"team_id": team_id, "user_id": user_id, "role": role})

def give_team_campaign_access(team_id: int, campaign_id: int):
    api_post("/team_campaign_access/", {"team_id": team_id, "campaign_id": campaign_id})

def give_team_workspace_access(team_id: int, workspace_id: int):
    api_post("/team_workspace_access/", {"team_id": team_id, "workspace_id": workspace_id})


# ---------------------------------------------------------------------------
# HELPERS: CAMPOS
# ---------------------------------------------------------------------------
_field_order_counter: dict[int, int] = {}

def _next_order(campaign_id: int) -> int:
    _field_order_counter[campaign_id] = _field_order_counter.get(campaign_id, 0) + 1
    return _field_order_counter[campaign_id]

def create_field(
    campaign_id: int,
    section_id: int,
    name: str = None,
    type_code: str = None,
    subtype_code: str = None,
    template_code: str = None,
    required: bool = False,
    is_primary: bool = False,
    nom_id: int = None,
    expression: str = None,
    default_value: str = None,
    is_visible: bool = True,
    title_order: int = None,
) -> int | None:
    order = _next_order(campaign_id)
    payload = {
        "campaign_id": campaign_id,
        "lead_field_section_id": section_id,
        "required": required,
        "is_primary": is_primary,
        "is_visible": is_visible,
        "order": order,
    }
    if default_value:
        payload["default_value"] = default_value
    if title_order:
        payload["title_order"] = title_order
    if template_code:
        payload["field_template_code"] = template_code
    else:
        payload["name"] = name
        payload["field_type_code"] = type_code
        if subtype_code:
            payload["field_subtype_code"] = subtype_code
        if nom_id:
            payload["nomenclator_id"] = nom_id
        if expression:
            payload["calculation_expression"] = expression

    r = api_post("/lead_fields/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"  Error creando field '{name or template_code}': {r.text}", "ERR", indent=4)
    return None


# ---------------------------------------------------------------------------
# HELPERS: REGLAS DE VALIDACIÓN
# ---------------------------------------------------------------------------
def add_validation_rule(field_id: int, template_code: str, params: dict = None, error_msg: str = None):
    payload = {
        "field_id": field_id,
        "template_code": template_code,
        "template_params": params or {},
    }
    if error_msg:
        payload["error_message"] = error_msg
    r = api_post("/validation_rules/", payload)
    if r.status_code not in (200, 201):
        log(f"  Regla '{template_code}' en field {field_id}: {r.text}", "WARN", indent=6)


# ---------------------------------------------------------------------------
# HELPERS: LEADS
# ---------------------------------------------------------------------------
def create_lead(campaign_id: int, values: list[dict], assigned_to_user_id: int = None, tag_ids: list = None) -> int | None:
    clean = [v for v in values if v.get("field_id") is not None and v.get("value") is not None]
    payload = {"campaign_id": campaign_id, "values": clean}
    if assigned_to_user_id is not None:
        payload["assigned_to_user_id"] = assigned_to_user_id
    if tag_ids:
        payload["tag_ids"] = tag_ids
    r = api_post("/leads/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    return None

def add_comment(lead_id: int, content: str, color: str = None):
    payload = {"lead_id": lead_id, "content": content}
    if color:
        payload["color"] = color
    api_post("/lead_comments/", payload)

def update_lead_fields(lead_id: int, campaign_id: int, values: list[dict]):
    clean = [v for v in values if v.get("field_id") is not None and v.get("value") is not None]
    if not clean:
        return
    api_put(f"/leads/{lead_id}", {"campaign_id": campaign_id, "values": clean})

def change_lead_state(lead_id: int, new_state_id: int, notes: str = None):
    payload = {"new_state_id": new_state_id}
    if notes:
        payload["notes"] = notes
    r = api_post(f"/leads/{lead_id}/change_state", payload)
    return r.status_code in (200, 201)

def advance_lead_through_flow(lead_id: int, transitions: list, target_steps: int):
    """
    Avanza un lead por el flujo de estados usando las transiciones disponibles.
    transitions: lista de dicts con from_state_id y to_state_id.
    target_steps: cuántos pasos avanzar como máximo.
    """
    # Primero obtenemos el estado actual del lead. current_state_id (int interno crudo,
    # Fase 4 sin migrar) NO sirve para change_state (espera public_uuid) -- usamos el objeto
    # anidado current_state.id, que sí es el public_uuid real y viene siempre presente en
    # LeadResponse (no hace falta detailed=true acá).
    r = api_get(f"/leads/{lead_id}", params={"detailed": "false"})
    if r.status_code != 200:
        return
    current_state_id = (r.json().get("current_state") or {}).get("id")
    if not current_state_id:
        return

    steps_done = 0
    for _ in range(target_steps):
        # Buscar transiciones válidas desde el estado actual (transitions viene de
        # get_flow_transitions(), que ahora pide detailed=true -- from_state/to_state
        # anidados con public_uuid real).
        valid_next = [
            t for t in transitions
            if t.get("from_state") and t["from_state"]["id"] == current_state_id
        ]
        if not valid_next:
            break
        chosen = random.choice(valid_next)
        new_state_id = chosen["to_state"]["id"]
        notes = random.choice([
            "Actualización de estado por gestión comercial.",
            "Cliente respondió positivamente.",
            "Se realizó el seguimiento correspondiente.",
            "Avance según proceso de ventas.",
            None
        ])
        ok = change_lead_state(lead_id, new_state_id, notes)
        if not ok:
            break
        current_state_id = new_state_id
        steps_done += 1
        time.sleep(0.05)  # Pequeña pausa para no saturar la API


def delete_lead(lead_id: int):
    api_delete(f"/leads/{lead_id}")


# ---------------------------------------------------------------------------
# HELPERS: VISTAS
# ---------------------------------------------------------------------------
def create_lead_view(campaign_id: int, name: str, view_type: str = "TABLE", visibility: str = "PUBLIC",
                      team_id: int = None, filters: dict = None, ui_config: dict = None, sort_config: dict = None) -> int | None:
    payload = {
        "campaign_id": campaign_id,
        "name": name,
        "visibility": visibility,
        "view_type": view_type,
        "filters": filters if filters is not None else {},
        "ui_config": ui_config if ui_config is not None else {},
        "sort_config": sort_config if sort_config is not None else {"sort_by": "created_at", "ascending": False},
    }
    if team_id:
        payload["team_id"] = team_id
    r = api_post("/lead_views/", payload)
    if r.status_code not in (200, 201):
        log(f"Error creando vista '{name}': {r.text}", "WARN")
        return None
    return r.json().get("id")


# ---------------------------------------------------------------------------
# HELPERS: POLÍTICAS DE ENRUTAMIENTO (v3)
# ---------------------------------------------------------------------------
def create_routing_policy(name: str, target_team_id: int, priority: int, conditions: list[dict],
                           campaign_id: int = None, logical_operator: str = "AND",
                           description: str = None) -> int | None:
    """
    Crea una política de enrutamiento v3 (POST /lead_routing_policies/), con sus
    condiciones en la misma llamada. Cada condición debe traer 'position' y,
    exactamente uno de 'lead_field_id' / 'native_field' más su modo
    (simple: operator + value_str | lista: operator in/not_in/eq_strict + value_list).
    """
    payload = {
        "name": name,
        "priority": priority,
        "logical_operator": logical_operator,
        "target_team_id": target_team_id,
        "conditions": conditions,
    }
    if campaign_id:
        payload["campaign_id"] = campaign_id
    if description:
        payload["description"] = description
    r = api_post("/lead_routing_policies/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando política de enrutamiento '{name}': {r.text}", "ERR")
    return None


# ---------------------------------------------------------------------------
# HELPERS: TAGS (ETIQUETAS)
# ---------------------------------------------------------------------------
def create_tag(name: str, color: str = "#3B82F6") -> int | None:
    r = api_post("/tags/", {"name": name, "color": color})
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando tag '{name}': {r.text}", "ERR")
    return None


# ---------------------------------------------------------------------------
# HELPERS: ESTADOS DE CONTACTO ("Estado" nativo del lead -- distinto de
# "Etapa"/current_state_id, que viene del flujo. Es un campo propio de la
# organización, con 4 valores por defecto creados por OrganizationService:
# No Contactado / Esperando Respuesta / En Conversación / Rechazado).
# ---------------------------------------------------------------------------
def get_org_contact_states() -> list:
    r = api_get("/lead_contact_states", params={"page_size": 50})
    return r.json().get("items", []) if r.status_code == 200 else []

def change_lead_contact_state(lead_id: int, new_contact_state_id, notes: str = None) -> bool:
    payload = {"new_contact_state_id": new_contact_state_id}
    if notes:
        payload["notes"] = notes
    r = api_post(f"/leads/{lead_id}/change_contact_state", payload)
    return r.status_code in (200, 201)


# ---------------------------------------------------------------------------
# HELPERS: AUTOMATIZACIONES DE CAMPOS (FIELD AUTOMATIONS)
# ---------------------------------------------------------------------------
def auto_cond(field_id, operator: str, value=None) -> dict:
    """Construye una condición atómica (RuleCondition) del árbol de una automatización."""
    return {"field_id": field_id, "operator": operator, "value": value}

def auto_group(operator: str, rules: list) -> dict:
    """Construye un grupo lógico (RuleGroup) de condiciones/subgrupos."""
    return {"operator": operator, "rules": rules}

def auto_action(type_: str, target_field_id, value=None, source_field_id=None, source_field_ids=None) -> dict:
    """Construye una acción (AutomationAction) del array 'actions' de una automatización."""
    d = {"type": type_, "target_field_id": target_field_id}
    if value is not None:
        d["value"] = value
    if source_field_id is not None:
        d["source_field_id"] = source_field_id
    if source_field_ids is not None:
        d["source_field_ids"] = source_field_ids
    return d

def create_field_automation(campaign_id, name: str, trigger_events: list[str], conditions: dict,
                             actions: list[dict], priority: int = 1, description: str = None) -> int | None:
    payload = {
        "campaign_id": campaign_id,
        "name": name,
        "trigger_events": trigger_events,
        "conditions": conditions,
        "actions": actions,
        "priority": priority,
    }
    if description:
        payload["description"] = description
    r = api_post("/field_automations/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando automatización '{name}': {r.text}", "ERR")
    return None


# ---------------------------------------------------------------------------
# HELPERS: FORMULARIOS WEB PÚBLICOS
# ---------------------------------------------------------------------------
def create_web_form(campaign_id, name: str, fields: list[dict], title: str = None, description: str = None,
                     theme_config: dict = None, success_message: str = None, redirect_url: str = None,
                     allowed_domains: list[str] = None, require_captcha: bool = False) -> int | None:
    payload = {
        "campaign_id": campaign_id,
        "name": name,
        "fields": fields,
        "require_captcha": require_captcha,
        "active": True,
    }
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if theme_config:
        payload["theme_config"] = theme_config
    if success_message:
        payload["success_message"] = success_message
    if redirect_url:
        payload["redirect_url"] = redirect_url
    if allowed_domains:
        payload["allowed_domains"] = allowed_domains
    r = api_post("/web_forms/", payload)
    if r.status_code in (200, 201):
        return r.json()["id"]
    log(f"Error creando formulario web '{name}': {r.text}", "ERR")
    return None


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 1  ███████████████████████
# Clínica y Salud — 150 leads en 3 campañas, con automatizaciones, tags,
# formulario web, validaciones personalizadas, vistas guardadas variadas
# y equipos con usuarios de distintos roles para probar permisos.
# ===========================================================================
def build_org_salud():
    log("ORGANIZACIÓN 1: Clínica & Salud", "STEP")

    org_id = create_organization(
        "MediCare Centro de Salud",
        "Red de clínicas privadas con foco en medicina preventiva y estética."
    )
    if not org_id:
        return
    set_tenant(org_id)
    log(f"Org creada ID={org_id}", indent=2)

    # -----------------------------------------------------------------------
    # USUARIOS (con roles de organización variados: admin / agent / viewer,
    # para poder probar permisos distintos en cada equipo)
    # -----------------------------------------------------------------------
    users_def = [
        # (nombre, email, role_code)
        ("Valentina Suárez",   "vsuarez@medicare.com",    "admin"),
        ("Rodrigo Fernández",  "rfernandez@medicare.com", "agent"),
        ("Camila Torres",      "ctorres@medicare.com",    "admin"),
        ("Julieta Gómez",      "jgomez@medicare.com",     "viewer"),
        ("Nicolás Herrera",    "nherrera@medicare.com",   "agent"),
        ("Agustina Molina",    "amolina@medicare.com",    "agent"),
        ("Franco Ibáñez",      "fibanez@medicare.com",    "viewer"),
        ("Bruno Acosta",       "bacosta@medicare.com",    "agent"),
        ("Lucía Paz",          "lpaz@medicare.com",       "viewer"),
    ]
    users_by_email: dict[str, dict] = {}
    for name, email, role_code in users_def:
        new_user_id = create_user(name, email, org_id, role_code=role_code)
        if new_user_id:
            users_by_email[email] = {"id": new_user_id, "name": name, "role_code": role_code}
    log(f"Usuarios creados: {len(users_by_email)}", indent=2)

    def uid(email: str):
        info = users_by_email.get(email)
        return info["id"] if info else None

    valentina = uid("vsuarez@medicare.com")
    rodrigo   = uid("rfernandez@medicare.com")
    camila    = uid("ctorres@medicare.com")
    julieta   = uid("jgomez@medicare.com")
    nicolas   = uid("nherrera@medicare.com")
    agustina  = uid("amolina@medicare.com")
    franco_i  = uid("fibanez@medicare.com")
    bruno     = uid("bacosta@medicare.com")
    lucia     = uid("lpaz@medicare.com")

    # -----------------------------------------------------------------------
    # ETIQUETAS (TAGS) DE LA ORGANIZACIÓN
    # -----------------------------------------------------------------------
    tag_defs = [
        ("VIP",               "#8E44AD"),
        ("Urgente",            "#E74C3C"),
        ("Primera Consulta",   "#3498DB"),
        ("Seguimiento",        "#16A085"),
        ("Deuda Pendiente",    "#D35400"),
        ("Reprogramado",       "#F39C12"),
        ("Alto Riesgo",        "#C0392B"),
        ("Referido",           "#2980B9"),
    ]
    tag_ids_all = []
    for tname, tcolor in tag_defs:
        tid = create_tag(tname, tcolor)
        if tid:
            tag_ids_all.append(tid)
    log(f"Tags creados: {len(tag_ids_all)}", indent=2)

    def random_tags(max_k: int = 2) -> list:
        """~30% de los leads quedan sin etiquetas; el resto recibe 1 o 2 al azar
        (se usa igual en las 3 campañas de la organización)."""
        if not tag_ids_all or random.random() > 0.7:
            return []
        k = random.randint(1, min(max_k, len(tag_ids_all)))
        return random.sample(tag_ids_all, k)

    # -----------------------------------------------------------------------
    # ESTADOS DE CONTACTO ("Estado" nativo -- distinto de la "Etapa" del flujo)
    # -----------------------------------------------------------------------
    items_contact_states = get_org_contact_states()
    log(f"Estados de contacto disponibles: {len(items_contact_states)}", indent=2)

    _contact_state_weights = {
        "No Contactado": 20, "Esperando Respuesta": 25,
        "En Conversación": 35, "Rechazado": 20,
    }

    def random_contact_state_id():
        """~75% de los leads reciben un cambio de Estado explícito (el resto
        queda en 'No Contactado', el valor inicial por defecto)."""
        if not items_contact_states:
            return None
        ids = [st["id"] for st in items_contact_states]
        weights = [_contact_state_weights.get(st.get("name"), 10) for st in items_contact_states]
        return random.choices(ids, weights=weights)[0]

    # -----------------------------------------------------------------------
    # NOMENCLADORES DE ORGANIZACIÓN
    # -----------------------------------------------------------------------
    items_obra_social, nom_obra_social = get_or_create_org_nomenclator(
        "Obra Social / Prepaga",
        ["OSDE", "Swiss Medical", "Galeno", "Medicus", "PAMI", "Particular", "Sancor Salud", "Accord Salud"]
    )
    items_especialidad, nom_especialidad = get_or_create_org_nomenclator(
        "Especialidad Médica",
        ["Clínica General", "Cardiología", "Dermatología", "Traumatología",
         "Ginecología", "Pediatría", "Nutrición", "Psicología", "Kinesiología"]
    )
    items_genero, _  = get_global_nomenclator("Genero")

    # -----------------------------------------------------------------------
    # WORKSPACES
    # -----------------------------------------------------------------------
    ws_pacientes    = create_workspace("Pacientes Generales",  "Gestión de pacientes ambulatorios")
    ws_estetica     = create_workspace("Medicina Estética",    "Tratamientos estéticos y cirugías menores")
    ws_telemedicina = create_workspace("Telemedicina",         "Consultas médicas a distancia (video/teléfono/chat)")

    # -----------------------------------------------------------------------
    # EQUIPOS
    # -----------------------------------------------------------------------
    team_admision  = create_team("Admisión y Recepción", visibility_shared=True)
    team_medicos   = create_team("Equipo Médico",         visibility_shared=False)
    team_telemed   = create_team("Equipo Telemedicina",   visibility_shared=True)

    if team_admision:
        if valentina:
            add_team_member(team_admision, valentina, "MANAGER")
        for u_ in (rodrigo, julieta):
            if u_:
                add_team_member(team_admision, u_, "AGENT")
    if team_medicos:
        if camila:
            add_team_member(team_medicos, camila, "MANAGER")
        for u_ in (agustina, franco_i):
            if u_:
                add_team_member(team_medicos, u_, "AGENT")
    if team_telemed:
        if nicolas:
            add_team_member(team_telemed, nicolas, "MANAGER")
        for u_ in (bruno, lucia):
            if u_:
                add_team_member(team_telemed, u_, "AGENT")

    # Dar acceso a los workspaces
    if team_admision and ws_pacientes:
        give_team_workspace_access(team_admision, ws_pacientes)
    if team_medicos and ws_estetica:
        give_team_workspace_access(team_medicos, ws_estetica)
    if team_telemed and ws_telemedicina:
        give_team_workspace_access(team_telemed, ws_telemedicina)

    # Tabla de credenciales para probar permisos (misma password para todos:
    # SEED_USER_PASSWORD, fija -- ver cabecera del script). Se imprime al final
    # y también se guarda en un archivo aparte (ver final de build_org_salud()).
    credentials_table = [
        {"team": "Admisión y Recepción", "team_role": "MANAGER", "org_role": "admin",  "name": "Valentina Suárez",  "email": "vsuarez@medicare.com"},
        {"team": "Admisión y Recepción", "team_role": "AGENT",   "org_role": "agent",  "name": "Rodrigo Fernández", "email": "rfernandez@medicare.com"},
        {"team": "Admisión y Recepción", "team_role": "AGENT",   "org_role": "viewer", "name": "Julieta Gómez",     "email": "jgomez@medicare.com"},
        {"team": "Equipo Médico",        "team_role": "MANAGER", "org_role": "admin",  "name": "Camila Torres",     "email": "ctorres@medicare.com"},
        {"team": "Equipo Médico",        "team_role": "AGENT",   "org_role": "agent",  "name": "Agustina Molina",   "email": "amolina@medicare.com"},
        {"team": "Equipo Médico",        "team_role": "AGENT",   "org_role": "viewer", "name": "Franco Ibáñez",     "email": "fibanez@medicare.com"},
        {"team": "Equipo Telemedicina",  "team_role": "MANAGER", "org_role": "agent",  "name": "Nicolás Herrera",   "email": "nherrera@medicare.com"},
        {"team": "Equipo Telemedicina",  "team_role": "AGENT",   "org_role": "agent",  "name": "Bruno Acosta",      "email": "bacosta@medicare.com"},
        {"team": "Equipo Telemedicina",  "team_role": "AGENT",   "org_role": "viewer", "name": "Lucía Paz",         "email": "lpaz@medicare.com"},
    ]

    flow_id      = get_default_flow(org_id)
    transitions  = get_flow_transitions(flow_id) if flow_id else []
    states       = get_flow_states(flow_id)      if flow_id else []
    initial_state = next((s for s in states if s.get("is_initial")), None)

    # -----------------------------------------------------------------------
    # FLUJO PERSONALIZADO: Medicina Estética
    # -----------------------------------------------------------------------
    estetica_states = [
        {"name": "Consulta Recibida",      "category": "OPEN", "is_initial": True,  "order": 1,  "color": "#6C8EBF"},
        {"name": "Evaluación Médica",      "category": "OPEN", "is_initial": False, "order": 2,  "color": "#82B366"},
        {"name": "Presupuesto Enviado",    "category": "OPEN", "is_initial": False, "order": 3,  "color": "#D6B656"},
        {"name": "Turno Confirmado",       "category": "OPEN", "is_initial": False, "order": 4,  "color": "#AE4132"},
        {"name": "Tratamiento en Curso",   "category": "OPEN", "is_initial": False, "order": 5,  "color": "#9673A6"},
        {"name": "Seguimiento Post-trat.", "category": "OPEN", "is_initial": False, "order": 6,  "color": "#7EA6E0"},
        {"name": "Paciente Fidelizado",    "category": "WON",  "is_initial": False, "order": None},
        {"name": "No Interesado",          "category": "LOST", "is_initial": False, "order": None},
        {"name": "Canceló Tratamiento",    "category": "LOST", "is_initial": False, "order": None},
    ]
    estetica_transitions = [
        (0,1),(1,2),(2,3),(3,4),(4,5),(5,6),   # happy path
        (0,7),(1,7),(2,7),(3,7),                # no interesado
        (3,8),(4,8),                            # canceló
        (5,7),                                  # post-trat -> no interesado
        (7,1),                                  # reingreso
    ]
    flow_estetica_id = create_custom_flow("Flujo Medicina Estética", estetica_states, estetica_transitions)
    transitions_estetica = get_flow_transitions(flow_estetica_id) if flow_estetica_id else []

    # -----------------------------------------------------------------------
    # FLUJO PERSONALIZADO: Telemedicina
    # -----------------------------------------------------------------------
    telemed_states = [
        {"name": "Solicitud Recibida",     "category": "OPEN", "is_initial": True,  "order": 1, "color": "#5B9BD5"},
        {"name": "Triage / Derivación",    "category": "OPEN", "is_initial": False, "order": 2, "color": "#70AD47"},
        {"name": "Consulta Agendada",      "category": "OPEN", "is_initial": False, "order": 3, "color": "#FFC000"},
        {"name": "Consulta Realizada",     "category": "WON",  "is_initial": False, "order": None},
        {"name": "No Asistió",             "category": "LOST", "is_initial": False, "order": None},
        {"name": "Cancelada por Paciente", "category": "LOST", "is_initial": False, "order": None},
    ]
    telemed_transitions = [
        (0,1),(1,2),(2,3),
        (0,4),(1,4),(2,4),
        (0,5),(1,5),(2,5),
        (4,0),(5,0),  # reingreso
    ]
    flow_telemed_id = create_custom_flow("Flujo Telemedicina", telemed_states, telemed_transitions)
    transitions_telemed = get_flow_transitions(flow_telemed_id) if flow_telemed_id else []

    # =========================================================================
    # CAMPAÑA 1: Pacientes Clínica General  (70 leads)
    # =========================================================================
    log("  Campaña: Pacientes Clínica General", "INFO")
    camp_pacientes = create_campaign("Pacientes Clínica General", ws_pacientes, is_public=False)
    if team_admision and camp_pacientes:
        give_team_campaign_access(team_admision, camp_pacientes)
    # Equipo Médico también recibe leads de Pacientes por la política de
    # enrutamiento "Coberturas Premium a Equipo Médico" (ver más abajo).
    if team_medicos and camp_pacientes:
        give_team_campaign_access(team_medicos, camp_pacientes)

    sec_personal  = get_or_create_section("Datos Personales")
    sec_medico    = get_or_create_section("Datos Médicos")
    sec_adicional = get_or_create_section("Información Adicional")

    f = {}
    lead_ids_pac = []
    if camp_pacientes:
        f["nombre"]       = create_field(camp_pacientes, sec_personal, template_code="FIRST_NAME",   required=True,  is_primary=True, title_order=1)
        f["apellido"]     = create_field(camp_pacientes, sec_personal, template_code="LAST_NAME",    required=True,  is_primary=True, title_order=2)
        f["dni"]          = create_field(camp_pacientes, sec_personal, template_code="DNI_ARG",       required=True,  is_primary=True)
        f["fecha_nac"]    = create_field(camp_pacientes, sec_personal, name="Fecha de Nacimiento", type_code="DATE", subtype_code="BIRTH_DATE",    required=True)
        _, _gnom = get_global_nomenclator("Genero")
        f["genero"]       = create_field(camp_pacientes, sec_personal, name="Género", type_code="SELECTOR",
                                          subtype_code="SELECTOR_SIMPLE", nom_id=_gnom)
        f["email"]        = create_field(camp_pacientes, sec_personal, name="Email",   type_code="STRING", subtype_code="EMAIL", required=True)
        f["telefono"]     = create_field(camp_pacientes, sec_personal, name="Teléfono",type_code="STRING",  subtype_code="MOBILE", required=True)

        items_os_camp, nom_os_camp = get_or_create_campaign_nomenclator(
            "Cobertura Médica", ["OSDE", "Swiss Medical", "Galeno", "PAMI", "Particular", "Sancor Salud"], camp_pacientes
        )
        f["obra_social"]  = create_field(camp_pacientes, sec_medico, name="Cobertura Médica",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_os_camp)
        f["peso"]         = create_field(camp_pacientes, sec_medico, name="Peso (kg)",   type_code="NUMBER")
        f["altura"]       = create_field(camp_pacientes, sec_medico, name="Altura (m)",  type_code="NUMBER")
        f["imc"]          = create_field(camp_pacientes, sec_medico, name="IMC",         type_code="CALCULATED",
                                          expression='IF(AND({Peso (kg)} > 0, {Altura (m)} > 0), ROUND({Peso (kg)} / ({Altura (m)} * {Altura (m)}), 2), 0)')
        f["estado_nutricional"] = create_field(camp_pacientes, sec_medico, name="Estado Nutricional", type_code="CALCULATED",
                                          expression='IF({IMC} = 0, "Sin datos", IF({IMC} < 18.5, "Bajo Peso", IF({IMC} < 25, "Normal", IF({IMC} < 30, "Sobrepeso", "Obesidad"))))')
        f["fumador"]      = create_field(camp_pacientes, sec_medico,    name="Fumador",          type_code="BOOL")
        f["tension"]      = create_field(camp_pacientes, sec_medico,    name="Tensión Arterial", type_code="STRING")
        f["alergias"]     = create_field(camp_pacientes, sec_adicional, name="Alergias Conocidas",type_code="STRING")
        f["notas"]        = create_field(camp_pacientes, sec_adicional, name="Notas Clínicas",   type_code="STRING")
        f["prox_turno"]   = create_field(camp_pacientes, sec_adicional, name="Próximo Turno",    type_code="DATE_TIME")
        # Nuevos: control preventivo (lo completa una automatización) y canal de
        # origen (lo completa el formulario web público, ver más abajo).
        f["control_preventivo"] = create_field(camp_pacientes, sec_adicional, name="Próximo Control Preventivo", type_code="DATE")
        f["canal_origen"]       = create_field(camp_pacientes, sec_adicional, name="Canal de Origen",            type_code="STRING")

        # --- Validaciones personalizadas (además de las que ya trae el template
        #     DNI_ARG -- ONLY_DIGITS/MIN_LENGTH/MAX_LENGTH -- y el subtipo MOBILE) ---
        if f.get("peso"):
            add_validation_rule(f["peso"],   "MIN_VALUE", {"limit": 20}, "El peso mínimo es 20 kg.")
            add_validation_rule(f["peso"],   "MAX_VALUE", {"limit": 300}, "El peso máximo es 300 kg.")
        if f.get("altura"):
            add_validation_rule(f["altura"], "MIN_VALUE", {"limit": 0.5}, "La altura mínima es 0.5 m.")
            add_validation_rule(f["altura"], "MAX_VALUE", {"limit": 2.5},  "La altura máxima es 2.5 m.")
        if f.get("telefono"):
            add_validation_rule(f["telefono"], "REGEX_MATCH", {"pattern": "^[+]549"}, "El teléfono debe ser un celular argentino (+549...).")
        if f.get("prox_turno"):
            add_validation_rule(f["prox_turno"], "DATE_FUTURE", {}, "El próximo turno debe ser una fecha futura.")

        create_lead_view(camp_pacientes, "Todos los Pacientes",       "TABLE",   "PUBLIC")
        create_lead_view(camp_pacientes, "Kanban por Estado",         "BOARD", "PUBLIC")

        # --- Políticas de enrutamiento (deben existir ANTES de crear los leads:
        #     el motor solo enruta en el momento de la creación) ---
        items_os_c, _ = get_or_create_campaign_nomenclator("Cobertura Médica",
            ["OSDE", "Swiss Medical", "Galeno", "PAMI", "Particular", "Sancor Salud"], camp_pacientes)
        item_particular = next((i for i in items_os_c if i["value"] == "Particular"), None)
        ids_premium = [i["id"] for i in items_os_c if i["value"] in ("OSDE", "Swiss Medical")]

        if team_admision and team_medicos and f.get("obra_social"):
            # Ejemplo de campo DINÁMICO (SELECTOR), modo simple: obra_social = "Particular"
            if item_particular:
                create_routing_policy(
                    "Particulares a Admisión", team_admision, priority=10,
                    campaign_id=camp_pacientes,
                    description="Pacientes sin cobertura médica (particulares) se asignan directo a Admisión.",
                    conditions=[{
                        "position": 0, "lead_field_id": f["obra_social"],
                        "operator": "eq", "value_str": str(item_particular["id"]),
                    }],
                )

            # Ejemplo de campo DINÁMICO (SELECTOR), modo lista: obra_social in [OSDE, Swiss Medical]
            if ids_premium:
                create_routing_policy(
                    "Coberturas Premium a Equipo Médico", team_medicos, priority=5,
                    campaign_id=camp_pacientes,
                    description="Pacientes con OSDE o Swiss Medical se derivan directo al equipo médico.",
                    conditions=[{
                        "position": 0, "lead_field_id": f["obra_social"],
                        "operator": "in", "value_list": [str(i) for i in ids_premium],
                    }],
                )

        # --- Vistas guardadas privadas y de equipo, con filtros y columnas propias ---
        if item_particular and f.get("obra_social"):
            create_lead_view(
                camp_pacientes, "Mis Pacientes Particulares", "TABLE", "PRIVATE",
                filters={"filters": [{"field_id": f["obra_social"], "operator": "eq", "value": item_particular["id"]}]},
                ui_config={"selected_ids": [fid for fid in (f.get("nombre"), f.get("apellido"), f.get("telefono"),
                                                             f.get("obra_social"), f.get("prox_turno")) if fid]},
            )
        # OJO: esta vista queda del lado de Equipo Médico (no Admisión), porque
        # es a ese equipo al que la política de enrutamiento "Coberturas Premium
        # a Equipo Médico" deriva estos leads apenas se crean.
        if team_medicos and ids_premium and f.get("obra_social"):
            create_lead_view(
                camp_pacientes, "Equipo Médico - Coberturas Premium", "TABLE", "TEAM", team_id=team_medicos,
                filters={"filters": [{"field_id": f["obra_social"], "operator": "in", "value": [str(i) for i in ids_premium]}]},
                ui_config={"selected_ids": [fid for fid in (f.get("nombre"), f.get("apellido"), f.get("obra_social"),
                                                             f.get("telefono"), f.get("prox_turno")) if fid]},
            )

        # --- Automatizaciones de campos (deben existir ANTES de crear los leads) ---
        if item_particular and f.get("obra_social") and f.get("nombre"):
            create_field_automation(
                camp_pacientes, "Cobertura por defecto: Particular", ["ON_CREATE"],
                auto_group("AND", [auto_cond(f["nombre"], "IS_NOT_EMPTY")]),
                [auto_action("SET_VALUE_IF_EMPTY", f["obra_social"], value=item_particular["id"])],
                priority=1, description="Si no se informó cobertura médica, se asume Particular.",
            )
        if f.get("email"):
            create_field_automation(
                camp_pacientes, "Normalizar email a minúsculas", ["ON_CREATE", "ON_UPDATE"],
                auto_group("AND", [auto_cond(f["email"], "IS_NOT_EMPTY")]),
                [auto_action("NORMALIZE_TEXT", f["email"], value="LOWERCASE")],
                priority=2, description="Evita duplicados por mayúsculas/minúsculas en el email.",
            )
        if f.get("control_preventivo") and f.get("nombre"):
            create_field_automation(
                camp_pacientes, "Agendar control preventivo a 30 días", ["ON_CREATE"],
                auto_group("AND", [auto_cond(f["nombre"], "IS_NOT_EMPTY")]),
                [auto_action("SET_DATE_OFFSET", f["control_preventivo"], value=30)],
                priority=3, description="Todo paciente nuevo recibe una fecha sugerida de control a 30 días.",
            )

        # --- Formulario web público: "Reservá tu turno" ---
        if f.get("nombre") and f.get("apellido") and f.get("email") and f.get("telefono"):
            web_form_fields = [
                {"lead_field_id": f["nombre"],   "order": 1, "is_required": True},
                {"lead_field_id": f["apellido"], "order": 2, "is_required": True},
                {"lead_field_id": f["email"],    "order": 3, "is_required": True, "custom_label": "Tu email"},
                {"lead_field_id": f["telefono"], "order": 4, "is_required": True, "custom_label": "Tu WhatsApp"},
            ]
            if f.get("obra_social"):
                web_form_fields.append({"lead_field_id": f["obra_social"], "order": 5, "is_required": False,
                                         "custom_label": "¿Tenés obra social o prepaga?"})
            if f.get("canal_origen"):
                # Campo oculto: no lo ve el paciente, el backend lo completa solo al crear el lead.
                web_form_fields.append({"lead_field_id": f["canal_origen"], "order": 6,
                                         "hidden_value": "Formulario Web - Landing Turnos"})
            create_web_form(
                camp_pacientes, "Landing Turnos - MediCare", web_form_fields,
                title="Reservá tu turno",
                description="Dejanos tus datos y te contactamos para coordinar tu consulta.",
                theme_config={"primary_color": "#2E86C1", "background_color": "#FFFFFF", "text_color": "#1F2937",
                              "button_text_color": "#FFFFFF", "border_radius": "8px", "font_family": "Inter, sans-serif"},
                success_message="¡Gracias! Un miembro de Admisión te va a contactar a la brevedad.",
                allowed_domains=["https://www.medicare-centrodesalud.com.ar"],
                require_captcha=False,
            )

        # --- Generar leads ---
        log("    Generando leads pacientes...", indent=4)
        items_g, _   = get_global_nomenclator("Genero")

        # Agentes de Admisión para simular algunos leads ya tomados (el resto queda sin asignar)
        admision_agent_ids = [u_ for u_ in (rodrigo, julieta) if u_]

        lead_ids_pac = []
        tagged_count_pac = 0
        for i in range(70):
            altura = round(random.uniform(1.50, 1.95), 2)
            peso   = round(random.uniform(48.0, 115.0), 1)
            imc_exp = round(peso / (altura * altura), 2)
            futuro  = datetime.now() + timedelta(days=random.randint(1, 60), hours=random.randint(8, 17))
            vals = [
                {"field_id": f["nombre"],    "value": fake.first_name()},
                {"field_id": f["apellido"],  "value": fake.last_name()},
                {"field_id": f["dni"],       "value": str(random.randint(10_000_000, 45_000_000))},
                {"field_id": f["fecha_nac"], "value": fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat()},
                {"field_id": f["email"],     "value": fake.email()},
                {"field_id": f["peso"],      "value": peso},
                {"field_id": f["altura"],    "value": altura},
                {"field_id": f["fumador"],   "value": random.choice(["true", "false"])},
            ]
            if f.get("genero") and items_g:
                vals.append({"field_id": f["genero"],      "value": rand_nom_id(items_g)})
            # ~25% de los leads llegan sin cobertura informada: la automatización
            # "Cobertura por defecto: Particular" se encarga de completarla.
            if f.get("obra_social") and items_os_c and random.random() > 0.25:
                vals.append({"field_id": f["obra_social"], "value": rand_nom_id(items_os_c)})
            if f.get("telefono") and random.random() > 0.2:
                vals.append({"field_id": f["telefono"],    "value": f"+549{random.randint(1100000000,1199999999)}"})
            if f.get("tension") and random.random() > 0.4:
                vals.append({"field_id": f["tension"],     "value": f"{random.randint(100,140)}/{random.randint(60,90)}"})
            if f.get("prox_turno") and random.random() > 0.5:
                vals.append({"field_id": f["prox_turno"],  "value": futuro.strftime("%Y-%m-%d %H:%M:%S")})
            if f.get("canal_origen") and random.random() > 0.8:
                vals.append({"field_id": f["canal_origen"], "value": random.choice(["Referido Interno", "Cartelería en Clínica"])})

            # ~40% de los leads quedan tomados por un agente puntual; el resto sin asignar
            asignado = random.choice(admision_agent_ids) if admision_agent_ids and random.random() < 0.4 else None

            tag_ids_for_lead = random_tags()
            lid = create_lead(camp_pacientes, vals, assigned_to_user_id=asignado, tag_ids=tag_ids_for_lead)
            if lid:
                lead_ids_pac.append((lid, imc_exp))
                if tag_ids_for_lead:
                    tagged_count_pac += 1

                # Verificar CALCULATED
                if random.random() < 0.15:
                    lr = api_get(f"/leads/{lid}", params={"detailed": "false"})
                    if lr.status_code == 200:
                        fvals = lr.json().get("field_values", [])
                        imc_field = next((fv for fv in fvals if fv.get("field_id") == f.get("imc")), None)
                        if imc_field and imc_field.get("value"):
                            try:
                                got = float(imc_field["value"])
                                if abs(got - imc_exp) > 0.1:
                                    warn_calculated("IMC", imc_exp, got)
                            except (ValueError, TypeError):
                                warn_calculated("IMC", imc_exp, imc_field.get("value"))

        # Avanzar estados y agregar comentarios (rango ampliado para que una
        # porción real de leads llegue a estados terminales, GANADO/PERDIDO,
        # y no se quede siempre en las primeras etapas)
        for idx, (lid, _) in enumerate(lead_ids_pac):
            steps = random.choices([0, 1, 2, 3, 4, 5, 6], weights=[8, 12, 15, 20, 20, 15, 10])[0]
            if steps > 0 and transitions:
                advance_lead_through_flow(lid, transitions, steps)

            # Variar el "Estado" de contacto (nativo, distinto de la "Etapa" del
            # flujo que ya se mueve arriba con advance_lead_through_flow).
            if items_contact_states and random.random() < 0.75:
                change_lead_contact_state(lid, random_contact_state_id())

            if random.random() > 0.5:
                comments = [
                    "Paciente refirió dolor lumbar crónico.",
                    "Se solicitaron análisis de laboratorio.",
                    "Turno confirmado para la semana próxima.",
                    "Paciente derivado a especialista.",
                    "Se adjuntó historia clínica previa.",
                    "Llamado sin respuesta, se dejó mensaje.",
                    "Paciente solicita cambio de turno.",
                ]
                add_comment(lid, random.choice(comments), random.choice(["#6C8EBF", "#82B366", "#D6B656", None]))

            # Algunos updates para auditoría
            if random.random() > 0.7 and f.get("tension"):
                update_lead_fields(lid, camp_pacientes, [
                    {"field_id": f["tension"], "value": f"{random.randint(100,145)}/{random.randint(60,95)}"}
                ])

        # Algunos deletes suaves para auditoría
        for lid, _ in random.sample(lead_ids_pac, min(3, len(lead_ids_pac))):
            delete_lead(lid)

        log(f"    {len(lead_ids_pac)} leads pacientes generados", indent=4)
        log(f"    Leads con etiquetas: {tagged_count_pac}/{len(lead_ids_pac)}", indent=4)

    # =========================================================================
    # CAMPAÑA 2: Medicina Estética (flujo personalizado)  (40 leads)
    # =========================================================================
    log("  Campaña: Medicina Estética", "INFO")
    camp_estetica = create_campaign("Consultas Estética", ws_estetica, lead_flow_id=flow_estetica_id, is_public=False)
    if team_medicos and camp_estetica:
        give_team_campaign_access(team_medicos, camp_estetica)

    sec_est_1 = get_or_create_section("Información del Paciente")
    sec_est_2 = get_or_create_section("Tratamiento Solicitado")
    sec_est_3 = get_or_create_section("Seguimiento")

    items_trat, nom_trat = get_or_create_campaign_nomenclator(
        "Tipo de Tratamiento",
        ["Botox", "Rellenos dérmicos", "Lifting facial", "Rinoplastia", "Blefaroplastia",
         "Liposucción", "Abdominoplastia", "Rejuvenecimiento láser", "Mesoterapia"],
        camp_estetica
    )
    items_zona, nom_zona = get_or_create_campaign_nomenclator(
        "Zona a Tratar",
        ["Rostro", "Cuello", "Abdomen", "Glúteos", "Piernas", "Brazos", "Mamas", "Espalda"],
        camp_estetica
    )

    fe = {}
    lead_ids_est = []
    if camp_estetica:
        fe["nombre"]      = create_field(camp_estetica, sec_est_1, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        fe["apellido"]    = create_field(camp_estetica, sec_est_1, template_code="LAST_NAME",  required=True, title_order=2)
        fe["email"]       = create_field(camp_estetica, sec_est_1, name="Email",    type_code="STRING", subtype_code="EMAIL", required=True, is_primary=True)
        fe["telefono"]    = create_field(camp_estetica, sec_est_1, name="Teléfono", type_code="STRING",  subtype_code="MOBILE", required=True)
        fe["edad"]        = create_field(camp_estetica, sec_est_1, template_code="AGE")
        fe["instagram"]   = create_field(camp_estetica, sec_est_1, template_code="INSTAGRAM_USER")
        fe["tratamiento"] = create_field(camp_estetica, sec_est_2, name="Tratamiento Solicitado",
                                          type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_trat)
        fe["zona"]        = create_field(camp_estetica, sec_est_2, name="Zona a Tratar",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_zona)
        fe["presupuesto"] = create_field(camp_estetica, sec_est_2, name="Presupuesto Aprobado (USD)", type_code="NUMBER", subtype_code="MONEY")
        fe["fecha_trat"]  = create_field(camp_estetica, sec_est_2, name="Fecha Tratamiento",          type_code="DATE_TIME")
        fe["sesiones"]    = create_field(camp_estetica, sec_est_2, name="Nro Sesiones",                type_code="INT",    default_value="1")
        fe["costo_ses"]   = create_field(camp_estetica, sec_est_2, name="Costo por Sesión (USD)",      type_code="NUMBER", subtype_code="MONEY")
        fe["costo_total"] = create_field(camp_estetica, sec_est_2, name="Costo Total (USD)",           type_code="CALCULATED",
                                          expression='{Nro Sesiones} * {Costo por Sesión (USD)}')
        fe["satisfaccion"]= create_field(camp_estetica, sec_est_3, name="Satisfacción",               type_code="NUMBER",  subtype_code="STAR_RATING")
        fe["notas_post"]  = create_field(camp_estetica, sec_est_3, name="Notas Post-Tratamiento",      type_code="STRING")
        fe["foto_antes"]  = create_field(camp_estetica, sec_est_3, name="Foto Antes",                  type_code="FILE",   subtype_code="FILE_IMAGE", is_visible=True)
        # Nuevos: prioridad de atención (la fija una automatización) y nombre
        # completo (armado automáticamente, ver automatizaciones más abajo).
        fe["prioridad"]       = create_field(camp_estetica, sec_est_2, name="Prioridad de Atención", type_code="STRING", default_value="Normal")
        fe["nombre_completo"] = create_field(camp_estetica, sec_est_1, name="Nombre Completo",        type_code="STRING")

        if fe.get("presupuesto"):
            add_validation_rule(fe["presupuesto"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(fe["presupuesto"], "MAX_VALUE", {"limit": 10000}, "El presupuesto máximo aprobable es USD 10.000.")
        if fe.get("sesiones"):
            add_validation_rule(fe["sesiones"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(fe["sesiones"], "MAX_VALUE", {"limit": 20})
        if fe.get("telefono"):
            add_validation_rule(fe["telefono"], "REGEX_MATCH", {"pattern": "^[+]549"}, "El teléfono debe ser un celular argentino (+549...).")

        create_lead_view(camp_estetica, "Pipeline Estética", "BOARD", "PUBLIC")

        # Política de enrutamiento (debe existir ANTES de crear los leads).
        # Ejemplo de campo NATIVO, política global (sin campaign_id): toda consulta
        # de la campaña de Estética se deriva al equipo médico.
        if team_medicos:
            create_routing_policy(
                "Consultas de Estética al Equipo Médico", team_medicos, priority=20,
                description="Política global: toda consulta de la campaña de Medicina Estética va al equipo médico.",
                conditions=[{
                    "position": 0, "native_field": "campaign_id",
                    "operator": "eq", "value_str": str(camp_estetica),
                }],
            )

        # Vistas guardadas privada y de equipo, con filtros y columnas propias
        if fe.get("satisfaccion"):
            create_lead_view(
                camp_estetica, "Seguimientos Pendientes (baja satisfacción)", "TABLE", "PRIVATE",
                filters={"filters": [{"field_id": fe["satisfaccion"], "operator": "lte", "value": 3}]},
                ui_config={"selected_ids": [fid for fid in (fe.get("nombre"), fe.get("apellido"), fe.get("tratamiento"),
                                                             fe.get("satisfaccion"), fe.get("notas_post")) if fid]},
            )
        if team_medicos and fe.get("presupuesto"):
            create_lead_view(
                camp_estetica, "Estética - Alto Presupuesto", "TABLE", "TEAM", team_id=team_medicos,
                filters={"filters": [{"field_id": fe["presupuesto"], "operator": "gte", "value": 3000}]},
                ui_config={"selected_ids": [fid for fid in (fe.get("nombre"), fe.get("apellido"), fe.get("tratamiento"),
                                                             fe.get("presupuesto"), fe.get("prioridad")) if fid]},
            )

        # Automatizaciones de campos (deben existir ANTES de crear los leads)
        if fe.get("presupuesto") and fe.get("prioridad"):
            create_field_automation(
                camp_estetica, "Prioridad alta por presupuesto elevado", ["ON_CREATE", "ON_UPDATE"],
                auto_group("AND", [auto_cond(fe["presupuesto"], "GREATER_THAN", 3000)]),
                [auto_action("SET_VALUE", fe["prioridad"], value="Alta")],
                priority=1, description="Presupuestos aprobados de más de USD 3000 se marcan como prioridad Alta.",
            )
        if fe.get("nombre_completo") and fe.get("apellido"):
            create_field_automation(
                camp_estetica, "Nombre completo automático", ["ON_CREATE", "ON_UPDATE"],
                auto_group("AND", [auto_cond(fe["apellido"], "IS_NOT_EMPTY")]),
                [auto_action("CONCAT_FIELDS", fe["nombre_completo"], value=" ",
                             source_field_ids=[fe["nombre"], fe["apellido"]])],
                priority=2, description="Combina Nombre + Apellido en un solo campo para listados/exportes.",
            )

        # Generar leads
        log("    Generando leads estética...", indent=4)
        # Agentes del Equipo Médico para simular algunos leads ya tomados
        medicos_agent_ids = [u_ for u_ in (agustina, franco_i) if u_]

        lead_ids_est = []
        tagged_count_est = 0
        for _ in range(40):
            sesiones   = random.randint(1, 8)
            costo_ses  = round(random.uniform(80, 600), 2)
            costo_tot_exp = round(sesiones * costo_ses, 2)
            futuro = datetime.now() + timedelta(days=random.randint(3, 90))
            vals = [
                {"field_id": fe["nombre"],    "value": fake.first_name()},
                {"field_id": fe["apellido"],  "value": fake.last_name()},
                {"field_id": fe["email"],     "value": fake.email()},
                {"field_id": fe["telefono"],  "value": f"+549{random.randint(1100000000,1199999999)}"},
                {"field_id": fe["sesiones"],  "value": sesiones},
                {"field_id": fe["costo_ses"], "value": costo_ses},
            ]
            if fe.get("edad"):
                vals.append({"field_id": fe["edad"],     "value": random.randint(18, 65)})
            if fe.get("zona") and items_zona:
                vals.append({"field_id": fe["zona"],     "value": rand_nom_id(items_zona)})
            if fe.get("tratamiento") and items_trat:
                vals.append({"field_id": fe["tratamiento"], "value": rand_nom_id(items_trat)})
            if fe.get("presupuesto") and random.random() > 0.3:
                vals.append({"field_id": fe["presupuesto"], "value": round(random.uniform(200, 5000), 2)})
            if fe.get("fecha_trat") and random.random() > 0.4:
                vals.append({"field_id": fe["fecha_trat"],  "value": futuro.strftime("%Y-%m-%d %H:%M:%S")})
            if fe.get("satisfaccion") and random.random() > 0.5:
                vals.append({"field_id": fe["satisfaccion"], "value": random.randint(1, 5)})
            if fe.get("instagram") and random.random() > 0.6:
                vals.append({"field_id": fe["instagram"],  "value": f"@{fake.user_name()}"})

            # ~40% de los leads quedan tomados por un agente puntual; el resto sin asignar
            asignado = random.choice(medicos_agent_ids) if medicos_agent_ids and random.random() < 0.4 else None

            tag_ids_for_lead = random_tags()
            lid = create_lead(camp_estetica, vals, assigned_to_user_id=asignado, tag_ids=tag_ids_for_lead)
            if lid:
                lead_ids_est.append((lid, costo_tot_exp))
                if tag_ids_for_lead:
                    tagged_count_est += 1

                # Check CALCULATED costo_total
                if random.random() < 0.2:
                    lr = api_get(f"/leads/{lid}", params={"detailed": "false"})
                    if lr.status_code == 200:
                        fvals = lr.json().get("field_values", [])
                        ct_fv = next((fv for fv in fvals if fv.get("field_id") == fe.get("costo_total")), None)
                        if ct_fv and ct_fv.get("value"):
                            try:
                                got = float(ct_fv["value"])
                                if abs(got - costo_tot_exp) > 0.5:
                                    warn_calculated("Costo Total", costo_tot_exp, got)
                            except (ValueError, TypeError):
                                warn_calculated("Costo Total", costo_tot_exp, ct_fv.get("value"))

        for lid, _ in lead_ids_est:
            steps = random.choices([0, 1, 2, 3, 4, 5, 6], weights=[6, 10, 15, 18, 18, 18, 15])[0]
            if steps > 0 and transitions_estetica:
                advance_lead_through_flow(lid, transitions_estetica, steps)
            if items_contact_states and random.random() < 0.75:
                change_lead_contact_state(lid, random_contact_state_id())
            if random.random() > 0.4:
                add_comment(lid, random.choice([
                    "Paciente interesada en paquete completo.",
                    "Se envió propuesta por email.",
                    "Confirmar disponibilidad del cirujano.",
                    "Solicita financiación en cuotas.",
                    "No responde llamados, intentar WhatsApp.",
                    "Turno de evaluación realizado con éxito.",
                ]))
            if random.random() > 0.65 and fe.get("satisfaccion"):
                update_lead_fields(lid, camp_estetica, [
                    {"field_id": fe["satisfaccion"], "value": random.randint(3, 5)}
                ])

        log(f"    {len(lead_ids_est)} leads estética generados", indent=4)
        log(f"    Leads con etiquetas: {tagged_count_est}/{len(lead_ids_est)}", indent=4)

    # =========================================================================
    # CAMPAÑA 3: Telemedicina / Consultas Virtuales (flujo personalizado)  (40 leads)
    # =========================================================================
    log("  Campaña: Telemedicina / Consultas Virtuales", "INFO")
    camp_telemed = create_campaign("Telemedicina / Consultas Virtuales", ws_telemedicina,
                                    lead_flow_id=flow_telemed_id, is_public=False)
    if team_telemed and camp_telemed:
        give_team_campaign_access(team_telemed, camp_telemed)
    # Equipo Médico también recibe las consultas urgentes de Telemedicina por
    # la política de enrutamiento "Telemedicina - Motivo Urgente al Equipo
    # Médico" (ver más abajo).
    if team_medicos and camp_telemed:
        give_team_campaign_access(team_medicos, camp_telemed)

    sec_tele_1 = get_or_create_section("Datos del Paciente")
    sec_tele_2 = get_or_create_section("Consulta Virtual")

    items_modalidad, nom_modalidad = get_or_create_campaign_nomenclator(
        "Modalidad de Contacto", ["WhatsApp", "Videollamada", "Teléfono"], camp_telemed
    )

    ft = {}
    lead_ids_tele = []
    if camp_telemed:
        ft["nombre"]    = create_field(camp_telemed, sec_tele_1, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        ft["apellido"]  = create_field(camp_telemed, sec_tele_1, template_code="LAST_NAME",  required=True, is_primary=True, title_order=2)
        # A propósito NO usamos el template DNI_ARG acá: es un campo STRING común
        # para poder agregarle nosotros mismos una regla REGEX_MATCH manual (modo
        # "experto") y no depender de las reglas que ya trae el template.
        ft["dni"]       = create_field(camp_telemed, sec_tele_1, name="DNI", type_code="STRING", required=True)
        ft["email"]     = create_field(camp_telemed, sec_tele_1, name="Email",   type_code="STRING", subtype_code="EMAIL", required=True)
        ft["telefono"]  = create_field(camp_telemed, sec_tele_1, name="Teléfono", type_code="STRING", subtype_code="MOBILE", required=True)
        ft["especialidad"] = create_field(camp_telemed, sec_tele_2, name="Especialidad Solicitada",
                                           type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_especialidad)
        ft["modalidad"] = create_field(camp_telemed, sec_tele_2, name="Modalidad de Contacto",
                                        type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_modalidad, required=True)
        ft["motivo"]    = create_field(camp_telemed, sec_tele_2, name="Motivo de Consulta", type_code="STRING")
        ft["es_primera_vez"] = create_field(camp_telemed, sec_tele_2, name="Es Primera Vez", type_code="BOOL")
        ft["fecha_consulta"] = create_field(camp_telemed, sec_tele_2, name="Fecha y Hora de Consulta", type_code="DATE_TIME")
        ft["costo_consulta"] = create_field(camp_telemed, sec_tele_2, name="Costo de Consulta (USD)", type_code="NUMBER", subtype_code="MONEY")
        # Sin subtipo URL a propósito: así la regla IS_URL que le agregamos abajo
        # es una validación nuestra, no la que trae por defecto ese subtipo.
        ft["link_videollamada"] = create_field(camp_telemed, sec_tele_2, name="Link de Videollamada", type_code="STRING")
        ft["satisfaccion"] = create_field(camp_telemed, sec_tele_2, name="Satisfacción", type_code="NUMBER", subtype_code="STAR_RATING")
        ft["contador_contactos"] = create_field(camp_telemed, sec_tele_2, name="Contador de Contactos", type_code="INT", default_value="0")

        # --- Validaciones personalizadas ---
        if ft.get("dni"):
            add_validation_rule(ft["dni"], "REGEX_MATCH", {"pattern": r"^\d{7,8}$"}, "El DNI debe tener 7 u 8 dígitos numéricos.")
        if ft.get("telefono"):
            add_validation_rule(ft["telefono"], "REGEX_MATCH", {"pattern": "^[+]549"}, "El teléfono debe ser un celular argentino (+549...).")
        if ft.get("motivo"):
            add_validation_rule(ft["motivo"], "MAX_LENGTH", {"limit": 300}, "El motivo de consulta no puede superar los 300 caracteres.")
        if ft.get("link_videollamada"):
            add_validation_rule(ft["link_videollamada"], "IS_URL", {}, "El link de videollamada debe ser una URL válida.")
        if ft.get("costo_consulta"):
            add_validation_rule(ft["costo_consulta"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(ft["costo_consulta"], "MAX_VALUE", {"limit": 5000}, "El costo de una consulta virtual no puede superar USD 5000.")
        if ft.get("fecha_consulta"):
            add_validation_rule(ft["fecha_consulta"], "DATE_FUTURE", {}, "La consulta debe agendarse a una fecha futura.")

        create_lead_view(camp_telemed, "Pipeline Telemedicina", "BOARD", "PUBLIC")

        item_videollamada = next((i for i in items_modalidad if i["value"] == "Videollamada"), None)

        # OJO: esta vista queda del lado de Equipo Médico (no Telemedicina),
        # porque es a ese equipo al que la política de enrutamiento "Telemedicina
        # - Motivo Urgente al Equipo Médico" deriva estos leads apenas se crean.
        if team_medicos and ft.get("motivo"):
            create_lead_view(
                camp_telemed, "Telemedicina - Urgentes Derivadas", "TABLE", "TEAM", team_id=team_medicos,
                filters={"filters": [{"field_id": ft["motivo"], "operator": "ilike", "value": "urgente"}]},
                ui_config={"selected_ids": [fid for fid in (ft.get("nombre"), ft.get("apellido"), ft.get("motivo"),
                                                             ft.get("modalidad"), ft.get("fecha_consulta")) if fid]},
            )

        # --- Políticas de enrutamiento (deben existir ANTES de crear los leads) ---
        if team_medicos and ft.get("motivo"):
            create_routing_policy(
                "Telemedicina - Motivo Urgente al Equipo Médico", team_medicos, priority=5,
                campaign_id=camp_telemed,
                description="Consultas virtuales cuyo motivo menciona 'urgente' se derivan directo al equipo médico presencial.",
                conditions=[{
                    "position": 0, "lead_field_id": ft["motivo"],
                    "operator": "ilike", "value_str": "urgente",
                }],
            )
        if team_telemed:
            create_routing_policy(
                "Telemedicina - Resto al Equipo de Telemedicina", team_telemed, priority=25,
                description="Política global: el resto de las consultas virtuales quedan en el equipo de Telemedicina.",
                conditions=[{
                    "position": 0, "native_field": "campaign_id",
                    "operator": "eq", "value_str": str(camp_telemed),
                }],
            )

        # --- Automatizaciones de campos (deben existir ANTES de crear los leads) ---
        if ft.get("telefono") and ft.get("contador_contactos"):
            create_field_automation(
                camp_telemed, "Contador de contactos", ["ON_UPDATE"],
                auto_group("AND", [auto_cond(ft["telefono"], "IS_NOT_EMPTY")]),
                [auto_action("INCREMENT", ft["contador_contactos"], value=1)],
                priority=1, description="Suma 1 cada vez que se actualiza el lead (aproximación a cantidad de contactos).",
            )
        if item_videollamada and ft.get("modalidad") and ft.get("link_videollamada"):
            create_field_automation(
                camp_telemed, "Link de videollamada por defecto", ["ON_CREATE", "ON_UPDATE"],
                auto_group("AND", [auto_cond(ft["modalidad"], "EQUALS", item_videollamada["id"])]),
                [auto_action("SET_VALUE_IF_EMPTY", ft["link_videollamada"], value="https://meet.medicare-salud.com.ar/sala-general")],
                priority=2, description="Si la modalidad es Videollamada y no hay link cargado, usa la sala general por defecto.",
            )

        # --- Generar leads ---
        log("    Generando leads telemedicina...", indent=4)
        telemed_agent_ids = [u_ for u_ in (bruno, lucia) if u_]
        motivos = [
            "Consulta de control de rutina.",
            "Renovación de receta de medicación crónica.",
            "Dolor de cabeza persistente, de baja intensidad.",
            "Fiebre alta y malestar general, caso urgente.",
            "Duda sobre resultados de análisis de laboratorio.",
            "Dolor abdominal intenso, requiere atención urgente.",
            "Seguimiento de tratamiento en curso.",
            "Erupción en la piel, consulta dermatológica.",
            "Control de presión arterial.",
            "Orientación nutricional.",
        ]

        lead_ids_tele = []
        tagged_count_tele = 0
        for _ in range(40):
            futuro = datetime.now() + timedelta(days=random.randint(1, 30), hours=random.randint(8, 20))
            vals = [
                {"field_id": ft["nombre"],   "value": fake.first_name()},
                {"field_id": ft["apellido"], "value": fake.last_name()},
                {"field_id": ft["dni"],      "value": str(random.randint(10_000_000, 45_000_000))},
                {"field_id": ft["email"],    "value": fake.email()},
                {"field_id": ft["telefono"], "value": f"+549{random.randint(1100000000,1199999999)}"},
                {"field_id": ft["es_primera_vez"], "value": random.choice(["true", "false"])},
            ]
            if ft.get("especialidad") and items_especialidad:
                vals.append({"field_id": ft["especialidad"], "value": rand_nom_id(items_especialidad)})
            if ft.get("modalidad") and items_modalidad:
                vals.append({"field_id": ft["modalidad"],    "value": rand_nom_id(items_modalidad)})
            if ft.get("motivo"):
                vals.append({"field_id": ft["motivo"],       "value": random.choice(motivos)})
            if ft.get("fecha_consulta") and random.random() > 0.3:
                vals.append({"field_id": ft["fecha_consulta"], "value": futuro.strftime("%Y-%m-%d %H:%M:%S")})
            if ft.get("costo_consulta") and random.random() > 0.2:
                vals.append({"field_id": ft["costo_consulta"], "value": round(random.uniform(15, 120), 2)})
            if ft.get("satisfaccion") and random.random() > 0.5:
                vals.append({"field_id": ft["satisfaccion"], "value": random.randint(1, 5)})

            asignado = random.choice(telemed_agent_ids) if telemed_agent_ids and random.random() < 0.4 else None

            tag_ids_for_lead = random_tags()
            lid = create_lead(camp_telemed, vals, assigned_to_user_id=asignado, tag_ids=tag_ids_for_lead)
            if lid:
                lead_ids_tele.append(lid)
                if tag_ids_for_lead:
                    tagged_count_tele += 1

        for lid in lead_ids_tele:
            steps = random.choices([0, 1, 2, 3], weights=[15, 25, 30, 30])[0]
            if steps > 0 and transitions_telemed:
                advance_lead_through_flow(lid, transitions_telemed, steps)
            if items_contact_states and random.random() < 0.75:
                change_lead_contact_state(lid, random_contact_state_id())
            if random.random() > 0.5:
                add_comment(lid, random.choice([
                    "Paciente conectado sin problemas, consulta realizada.",
                    "Se reprogramó la videollamada por problemas de conexión.",
                    "Se envió receta digital por email.",
                    "Paciente no se conectó a la hora pactada.",
                    "Se derivó a especialidad presencial.",
                ]))

        log(f"    {len(lead_ids_tele)} leads telemedicina generados", indent=4)
        log(f"    Leads con etiquetas: {tagged_count_tele}/{len(lead_ids_tele)}", indent=4)

    total_leads = len(lead_ids_pac) + len(lead_ids_est) + len(lead_ids_tele)
    log(f"Total de leads generados en Salud: {total_leads}", indent=2)

    # -----------------------------------------------------------------------
    # CREDENCIALES: se imprimen y además se guardan en un archivo aparte para
    # poder probar los permisos de cada equipo/rol sin volver a correr el script.
    # -----------------------------------------------------------------------
    log("Credenciales para probar permisos (misma password para todos):", "INFO", indent=2)
    log(f"Password: {SEED_USER_PASSWORD}", "INFO", indent=4)
    for row in credentials_table:
        log(f"[{row['team']}] {row['name']} <{row['email']}> — rol org: {row['org_role']} / rol equipo: {row['team_role']}",
            "INFO", indent=4)

    try:
        creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CREDENCIALES_SALUD.md")
        lines = [
            "# Credenciales de prueba — MediCare Centro de Salud\n",
            "\n",
            f"Password para **todos** los usuarios: `{SEED_USER_PASSWORD}`\n",
            "\n",
            "| Equipo | Usuario | Email | Rol de Organización | Rol de Equipo |\n",
            "|---|---|---|---|---|\n",
        ]
        for row in credentials_table:
            lines.append(f"| {row['team']} | {row['name']} | {row['email']} | {row['org_role']} | {row['team_role']} |\n")
        with open(creds_path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        log(f"Credenciales guardadas en {creds_path}", "OK", indent=2)
    except OSError as e:
        log(f"No se pudo escribir el archivo de credenciales: {e}", "WARN", indent=2)

    log(f"Organización SALUD completada ✓", indent=2)


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 2  ███████████████████████
# Inmobiliaria — volumen ALTO (1200 leads aprox)
# ===========================================================================
def build_org_inmobiliaria():
    log("ORGANIZACIÓN 2: Inmobiliaria (alto volumen)", "STEP")

    org_id = create_organization(
        "Propiedades del Sur S.A.",
        "Inmobiliaria boutique con operaciones en CABA, GBA y Mendoza."
    )
    if not org_id:
        return
    set_tenant(org_id)
    log(f"Org creada ID={org_id}", indent=2)

    # --- 10 usuarios ---
    users = []
    agentes_data = [
        ("Lucas Martínez",    "lmartinez@propiedadesdelsur.com"),
        ("Sofía Benítez",     "sbenitez@propiedadesdelsur.com"),
        ("Tomás Ríos",        "trios@propiedadesdelsur.com"),
        ("María Burgos",      "mburgos@propiedadesdelsur.com"),
        ("Ignacio Peralta",   "iperalta@propiedadesdelsur.com"),
        ("Florencia Núñez",   "fnunez@propiedadesdelsur.com"),
        ("Sebastián Castro",  "scastro@propiedadesdelsur.com"),
        ("Paula Giménez",     "pgimenez@propiedadesdelsur.com"),
        ("Agustín López",     "alopez@propiedadesdelsur.com"),
        ("Natalia Vega",      "nvega@propiedadesdelsur.com"),
    ]
    for name, email in agentes_data:
        uid = create_user(name, email, org_id)
        if uid:
            users.append(uid)
    log(f"Usuarios creados: {len(users)}", indent=2)

    # --- Nomencladores ---
    items_tipo_prop, nom_tipo_prop = get_or_create_org_nomenclator(
        "Tipo de Propiedad",
        ["Departamento", "Casa", "PH", "Lote", "Local Comercial", "Oficina", "Cochera", "Galpon", "Campo"]
    )
    items_operacion, nom_operacion = get_or_create_org_nomenclator(
        "Tipo de Operación",
        ["Venta", "Alquiler Tradicional", "Alquiler Temporario", "Permuta", "Venta + Alquiler"]
    )
    items_zona_prop, nom_zona_prop = get_or_create_org_nomenclator(
        "Zona de Interés",
        ["Palermo", "Belgrano", "Recoleta", "San Telmo", "Caballito", "Flores",
         "GBA Norte", "GBA Sur", "GBA Oeste", "Mendoza Capital", "Luján de Cuyo", "Maipú"]
    )
    items_estado_prop, nom_estado_prop = get_or_create_org_nomenclator(
        "Estado de la Propiedad",
        ["A estrenar", "Muy bueno", "Bueno", "A refaccionar", "En construcción"]
    )

    # --- Workspaces ---
    ws_ventas    = create_workspace("Ventas",    "Operaciones de compraventa")
    ws_alquileres= create_workspace("Alquileres","Operaciones de locación")
    ws_inversores= create_workspace("Inversores","Clientes inversores y desarrolladores")

    # --- Equipos ---
    team_ventas    = create_team("Equipo Ventas",     visibility_shared=True)
    team_alq       = create_team("Equipo Alquileres", visibility_shared=True)
    team_inversores= create_team("Equipo Inversores", visibility_shared=False)

    if users:
        if team_ventas:
            add_team_member(team_ventas, users[0], "MANAGER")
            for u in users[1:4]:
                add_team_member(team_ventas, u, "AGENT")
        if team_alq:
            add_team_member(team_alq, users[4], "MANAGER")
            for u in users[5:8]:
                add_team_member(team_alq, u, "AGENT")
        if team_inversores:
            add_team_member(team_inversores, users[8], "MANAGER")
            if len(users) > 9:
                add_team_member(team_inversores, users[9], "AGENT")

    if team_ventas    and ws_ventas:     give_team_workspace_access(team_ventas,     ws_ventas)
    if team_alq       and ws_alquileres: give_team_workspace_access(team_alq,        ws_alquileres)
    if team_inversores and ws_inversores:give_team_workspace_access(team_inversores, ws_inversores)

    flow_id     = get_default_flow(org_id)
    transitions = get_flow_transitions(flow_id) if flow_id else []

    sec_contacto = get_or_create_section("Datos de Contacto")
    sec_busqueda = get_or_create_section("Búsqueda")
    sec_finanzas = get_or_create_section("Aspectos Financieros")
    sec_seguimiento = get_or_create_section("Seguimiento Comercial")

    # -----------------------------------------------------------------------
    # Función reutilizable para crear campos de campaña inmobiliaria
    # -----------------------------------------------------------------------
    def setup_camp_inmob(camp_id: int, tipo_operacion: str) -> dict:
        flds = {}
        flds["nombre"]     = create_field(camp_id, sec_contacto, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        flds["apellido"]   = create_field(camp_id, sec_contacto, template_code="LAST_NAME",  required=True, title_order=2)
        flds["email"]      = create_field(camp_id, sec_contacto, name="Email",    type_code="STRING", subtype_code="EMAIL", required=True, is_primary=True)
        flds["telefono"]   = create_field(camp_id, sec_contacto, name="Teléfono", type_code="STRING",  subtype_code="MOBILE", required=True)
        flds["whatsapp"]   = create_field(camp_id, sec_contacto, name="WhatsApp", type_code="STRING",  subtype_code="WHATSAPP")
        flds["dni"]        = create_field(camp_id, sec_contacto, template_code="DNI_ARG")
        flds["tipo_prop"]  = create_field(camp_id, sec_busqueda, name="Tipo de Propiedad",
                                           type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_tipo_prop)
        flds["zona"]       = create_field(camp_id, sec_busqueda, name="Zona de Interés",
                                           type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_zona_prop)
        flds["ambientes"]  = create_field(camp_id, sec_busqueda, name="Ambientes Mínimos", type_code="INT")
        flds["sup_min"]    = create_field(camp_id, sec_busqueda, name="Superficie Mínima (m²)", type_code="INT")
        flds["sup_max"]    = create_field(camp_id, sec_busqueda, name="Superficie Máxima (m²)", type_code="INT")
        flds["cochera"]    = create_field(camp_id, sec_busqueda, name="Requiere Cochera",       type_code="BOOL", default_value="false")
        flds["estado_prop"]= create_field(camp_id, sec_busqueda, name="Estado Propiedad",
                                           type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_estado_prop)

        if tipo_operacion in ("venta", "inversores"):
            flds["presup_usd"]  = create_field(camp_id, sec_finanzas, name="Presupuesto (USD)",     type_code="NUMBER", subtype_code="MONEY")
            flds["financiado"]  = create_field(camp_id, sec_finanzas, name="Busca Financiamiento",  type_code="BOOL", default_value="false")
            flds["cuotas"]      = create_field(camp_id, sec_finanzas, name="Cuotas Disponibles",    type_code="INT")
            flds["rentabilidad"]= create_field(camp_id, sec_finanzas, name="Rentabilidad Esperada (%)", type_code="CALCULATED",
                                               expression='IF({Presupuesto (USD)} > 0, ROUND(({Presupuesto (USD)} * 0.06), 0), 0)')
        else:
            flds["alquiler_max"]= create_field(camp_id, sec_finanzas, name="Alquiler Máximo (ARS)", type_code="NUMBER", subtype_code="MONEY")
            flds["expensas_max"]= create_field(camp_id, sec_finanzas, name="Expensas Máximas (ARS)",type_code="NUMBER", subtype_code="MONEY")
            flds["total_max"]   = create_field(camp_id, sec_finanzas, name="Total Máximo (ARS)",    type_code="CALCULATED",
                                               expression='{Alquiler Máximo (ARS)} + {Expensas Máximas (ARS)}')

        flds["canal_origen"] = create_field(camp_id, sec_seguimiento, name="Canal de Origen",  type_code="STRING")
        flds["primer_cont"]  = create_field(camp_id, sec_seguimiento, name="Primer Contacto",   type_code="DATE_TIME")
        flds["ult_seguim"]   = create_field(camp_id, sec_seguimiento, name="Último Seguimiento",type_code="DATE_TIME")
        flds["rating_cli"]   = create_field(camp_id, sec_seguimiento, name="Calidad del Lead",  type_code="NUMBER",  subtype_code="NPS")
        flds["notas"]        = create_field(camp_id, sec_seguimiento, name="Notas Comerciales", type_code="STRING")
        flds["website_ref"]  = create_field(camp_id, sec_seguimiento, name="Sitio Web Referido",type_code="STRING",  subtype_code="WEBSITE")

        # Validaciones
        if flds.get("ambientes"):
            add_validation_rule(flds["ambientes"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(flds["ambientes"], "MAX_VALUE", {"limit": 10})
        if flds.get("sup_min"):
            add_validation_rule(flds["sup_min"], "MIN_VALUE", {"limit": 10})
        if flds.get("rating_cli"):
            add_validation_rule(flds["rating_cli"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(flds["rating_cli"], "MAX_VALUE", {"limit": 10})

        return flds

    # -----------------------------------------------------------------------
    # 3 CAMPAÑAS
    # -----------------------------------------------------------------------
    canales = ["Portal Zonaprop", "Instagram Ads", "Google Ads", "Referido", "Cartel", "Web propia", "Facebook", "WhatsApp directo"]

    def gen_leads_inmob(camp_id, flds, n, tipo):
        lead_ids = []
        for _ in range(n):
            sup_min = random.randint(30, 120)
            sup_max = sup_min + random.randint(10, 80)
            primer  = datetime.now() - timedelta(days=random.randint(1, 180))
            vals = [
                {"field_id": flds["nombre"],    "value": fake.first_name()},
                {"field_id": flds["apellido"],  "value": fake.last_name()},
                {"field_id": flds["email"],     "value": fake.email()},
                {"field_id": flds["telefono"],  "value": f"+549{random.randint(1100000000,1199999999)}"},
            ]
            if flds.get("dni") and random.random() > 0.3:
                vals.append({"field_id": flds["dni"],       "value": str(random.randint(10_000_000,45_000_000))})
            if flds.get("tipo_prop") and items_tipo_prop:
                vals.append({"field_id": flds["tipo_prop"],  "value": rand_nom_id(items_tipo_prop)})
            if flds.get("zona") and items_zona_prop:
                vals.append({"field_id": flds["zona"],       "value": rand_nom_ids(items_zona_prop, 2)})
            if flds.get("ambientes"):
                vals.append({"field_id": flds["ambientes"],  "value": random.randint(1, 5)})
            if flds.get("sup_min"):
                vals.append({"field_id": flds["sup_min"],    "value": sup_min})
            if flds.get("sup_max"):
                vals.append({"field_id": flds["sup_max"],    "value": sup_max})
            if flds.get("cochera"):
                vals.append({"field_id": flds["cochera"],    "value": random.choice(["true","false"])})
            if flds.get("estado_prop") and items_estado_prop:
                vals.append({"field_id": flds["estado_prop"],"value": rand_nom_id(items_estado_prop)})
            if flds.get("canal_origen"):
                vals.append({"field_id": flds["canal_origen"],"value": random.choice(canales)})
            if flds.get("primer_cont"):
                vals.append({"field_id": flds["primer_cont"],"value": primer.strftime("%Y-%m-%d %H:%M:%S")})
            if flds.get("rating_cli") and random.random() > 0.4:
                vals.append({"field_id": flds["rating_cli"], "value": random.randint(1, 10)})
            if flds.get("whatsapp") and random.random() > 0.5:
                vals.append({"field_id": flds["whatsapp"],   "value": f"+549{random.randint(1100000000,1199999999)}"})

            # Financieros según tipo
            if tipo in ("venta", "inversores") and flds.get("presup_usd"):
                pbase = random.randint(50_000, 600_000)
                vals.append({"field_id": flds["presup_usd"], "value": pbase})
                if flds.get("financiado"):
                    vals.append({"field_id": flds["financiado"], "value": random.choice(["true","false"])})
            elif tipo == "alquiler":
                if flds.get("alquiler_max"):
                    alq = random.randint(80_000, 350_000)
                    vals.append({"field_id": flds["alquiler_max"], "value": alq})
                if flds.get("expensas_max"):
                    exp = random.randint(5_000, 40_000)
                    vals.append({"field_id": flds["expensas_max"], "value": exp})

            lid = create_lead(camp_id, vals)
            if lid:
                lead_ids.append(lid)
        return lead_ids

    # Campaña A: Compradores
    log("  Campaña: Búsqueda de Propiedades (Ventas)", "INFO")
    camp_ventas = create_campaign("Búsqueda de Propiedades", ws_ventas)
    if team_ventas and camp_ventas:
        give_team_campaign_access(team_ventas, camp_ventas)
    flds_v = setup_camp_inmob(camp_ventas, "venta") if camp_ventas else {}
    create_lead_view(camp_ventas, "Pipeline Ventas", "BOARD", "PUBLIC") if camp_ventas else None
    lead_ids_v = gen_leads_inmob(camp_ventas, flds_v, 120, "venta") if camp_ventas and flds_v else []
    log(f"    {len(lead_ids_v)} leads ventas", indent=4)

    # Campaña B: Alquileres
    log("  Campaña: Búsqueda de Alquiler", "INFO")
    camp_alq = create_campaign("Búsqueda de Alquiler", ws_alquileres)
    if team_alq and camp_alq:
        give_team_campaign_access(team_alq, camp_alq)
    flds_a = setup_camp_inmob(camp_alq, "alquiler") if camp_alq else {}
    create_lead_view(camp_alq, "Pipeline Alquileres", "BOARD", "PUBLIC") if camp_alq else None
    lead_ids_a = gen_leads_inmob(camp_alq, flds_a, 120, "alquiler") if camp_alq and flds_a else []
    log(f"    {len(lead_ids_a)} leads alquileres", indent=4)

    # Campaña C: Inversores
    log("  Campaña: Inversores y Desarrolladores", "INFO")
    camp_inv = create_campaign("Inversores y Desarrolladores", ws_inversores)
    if team_inversores and camp_inv:
        give_team_campaign_access(team_inversores, camp_inv)
    flds_i = setup_camp_inmob(camp_inv, "inversores") if camp_inv else {}
    create_lead_view(camp_inv, "Pipeline Inversores", "TABLE", "PUBLIC") if camp_inv else None
    lead_ids_i = gen_leads_inmob(camp_inv, flds_i, 200, "inversores") if camp_inv and flds_i else []
    log(f"    {len(lead_ids_i)} leads inversores", indent=4)

    # Avance de estados, comentarios y updates (muestra por lote)
    log("  Avanzando estados y generando auditoría...", "INFO")
    comentarios_inmob = [
        "Interesado en el departamento de Palermo. Pedir info de expensas.",
        "No responde al llamado, reintentar esta tarde.",
        "Visita coordinada para el sábado a las 11hs.",
        "Enviar tasación actualizada por email.",
        "Cliente dice que el precio le parece alto, explorar descuento.",
        "Se mandó propuesta formal con tres opciones.",
        "Aprobó el crédito hipotecario, avanzar con escritura.",
        "Canceló la visita, reprogramar para próxima semana.",
        "Cliente muy interesado, pide exclusividad 10 días.",
        "Solicita informe de deudas del inmueble.",
    ]
    all_leads = lead_ids_v + lead_ids_a + lead_ids_i
    for lid in all_leads:
        steps = random.choices([0, 1, 2, 3, 4], weights=[20, 30, 25, 15, 10])[0]
        if steps > 0 and transitions:
            advance_lead_through_flow(lid, transitions, steps)
        if random.random() > 0.55:
            add_comment(lid, random.choice(comentarios_inmob))
        if random.random() > 0.75:
            # Update de rating o notas para auditoría
            camp_map = {}
            if lid in lead_ids_v and flds_v.get("rating_cli"):
                camp_map = (camp_ventas, flds_v["rating_cli"])
            elif lid in lead_ids_a and flds_a.get("rating_cli"):
                camp_map = (camp_alq, flds_a["rating_cli"])
            elif lid in lead_ids_i and flds_i.get("rating_cli"):
                camp_map = (camp_inv, flds_i["rating_cli"])
            if camp_map:
                update_lead_fields(lid, camp_map[0], [{"field_id": camp_map[1], "value": random.randint(1, 10)}])

    # Algunos deletes
    for lid in random.sample(all_leads, min(15, len(all_leads))):
        delete_lead(lid)

    log(f"Organización INMOBILIARIA completada ✓", indent=2)


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 3  ███████████████████████
# Fintech / Préstamos — volumen ALTO (500 leads)
# ===========================================================================
def build_org_fintech():
    log("ORGANIZACIÓN 3: Fintech / Créditos Personales (alto volumen)", "STEP")

    org_id = create_organization(
        "CréditoFácil S.A.",
        "Empresa de créditos personales y refinanciación online."
    )
    if not org_id:
        return
    set_tenant(org_id)
    log(f"Org creada ID={org_id}", indent=2)

    # Usuarios
    users = []
    for name, email in [
        ("Gonzalo Ramírez",   "gramírez@creditofacil.com"),
        ("Verónica Salinas",  "vsalinas@creditofacil.com"),
        ("Martín Díaz",       "mdiaz@creditofacil.com"),
    ]:
        uid = create_user(name, email, org_id)
        if uid:
            users.append(uid)

    # Nomencladores
    items_destino, nom_destino = get_or_create_org_nomenclator(
        "Destino del Crédito",
        ["Capital de trabajo", "Consumo personal", "Refacción del hogar", "Educación",
         "Salud", "Vehículo", "Refinanciación de deuda", "Viaje", "Otro"]
    )
    items_situacion, nom_situacion = get_or_create_org_nomenclator(
        "Situación Laboral",
        ["Relación de Dependencia", "Monotributista", "Autónomo", "Jubilado/Pensionado",
         "Desempleado", "Empresario"]
    )
    items_genero, _ = get_global_nomenclator("Genero")

    ws_prestamos = create_workspace("Solicitudes de Préstamos")
    ws_recup     = create_workspace("Recupero de Deuda")

    team_analistas = create_team("Analistas de Crédito", visibility_shared=True)
    team_recup     = create_team("Equipo Recupero",      visibility_shared=False)
    if users:
        if team_analistas:
            add_team_member(team_analistas, users[0], "MANAGER")
            if len(users) > 1:
                add_team_member(team_analistas, users[1], "AGENT")
        if team_recup and len(users) > 2:
            add_team_member(team_recup, users[2], "MANAGER")
    if team_analistas and ws_prestamos: give_team_workspace_access(team_analistas, ws_prestamos)
    if team_recup     and ws_recup:     give_team_workspace_access(team_recup,     ws_recup)

    flow_id     = get_default_flow(org_id)
    transitions = get_flow_transitions(flow_id) if flow_id else []

    sec_sol   = get_or_create_section("Datos del Solicitante")
    sec_cred  = get_or_create_section("Solicitud de Crédito")
    sec_anal  = get_or_create_section("Análisis Crediticio")

    # -----------------------------------------------------------------------
    # CAMPAÑA: Solicitudes de Crédito
    # -----------------------------------------------------------------------
    log("  Campaña: Solicitudes de Crédito Personal", "INFO")
    camp_cred = create_campaign("Crédito Personal Express", ws_prestamos)
    if team_analistas and camp_cred:
        give_team_campaign_access(team_analistas, camp_cred)

    fc = {}
    if camp_cred:
        fc["nombre"]      = create_field(camp_cred, sec_sol, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        fc["apellido"]    = create_field(camp_cred, sec_sol, template_code="LAST_NAME",  required=True, title_order=2)
        fc["dni"]         = create_field(camp_cred, sec_sol, template_code="DNI_ARG",     required=True, is_primary=True)
        fc["cuit"]        = create_field(camp_cred, sec_sol, template_code="CUIT_CUIL")
        fc["fecha_nac"]   = create_field(camp_cred, sec_sol, template_code="BIRTH_DATE_ADULT")
        fc["email"]       = create_field(camp_cred, sec_sol, name="Email",    type_code="STRING", subtype_code="EMAIL", required=True)
        fc["telefono"]    = create_field(camp_cred, sec_sol, name="Teléfono", type_code="STRING",  subtype_code="MOBILE", required=True)
        _, _gnom = get_global_nomenclator("Genero")
        fc["genero"]      = create_field(camp_cred, sec_sol, name="Género",   type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=_gnom)
        fc["situacion"]   = create_field(camp_cred, sec_sol, name="Situación Laboral",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_situacion)

        fc["monto_solic"] = create_field(camp_cred, sec_cred, name="Monto Solicitado (ARS)", type_code="NUMBER", subtype_code="MONEY",  required=True)
        fc["plazo"]       = create_field(camp_cred, sec_cred, name="Plazo (meses)",          type_code="INT",    required=True)
        fc["destino"]     = create_field(camp_cred, sec_cred, name="Destino del Crédito",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_destino)
        fc["ingreso"]     = create_field(camp_cred, sec_cred, name="Ingreso Mensual (ARS)",  type_code="NUMBER", subtype_code="MONEY")
        fc["relacion"]    = create_field(camp_cred, sec_anal, name="Relación Cuota/Ingreso (%)", type_code="CALCULATED",
                                          expression='IF(AND({Ingreso Mensual (ARS)} > 0, {Plazo (meses)} > 0), ROUND(({Monto Solicitado (ARS)} / {Plazo (meses)}) / {Ingreso Mensual (ARS)} * 100, 1), 0)')
        fc["riesgo"]      = create_field(camp_cred, sec_anal, name="Nivel de Riesgo",         type_code="CALCULATED",
                                          expression='IF({Relación Cuota/Ingreso (%)} = 0, "Sin datos", IF({Relación Cuota/Ingreso (%)} <= 25, "Bajo", IF({Relación Cuota/Ingreso (%)} <= 40, "Medio", "Alto")))')
        fc["score"]       = create_field(camp_cred, sec_anal, name="Score Crediticio",         type_code="INT")
        fc["aprobado"]    = create_field(camp_cred, sec_anal, name="Monto Aprobado (ARS)",     type_code="NUMBER", subtype_code="MONEY")
        fc["tasa"]        = create_field(camp_cred, sec_anal, name="Tasa Aplicada (%)",        type_code="NUMBER", subtype_code="PERCENTAGE")
        fc["obs"]         = create_field(camp_cred, sec_anal, name="Observaciones Analista",   type_code="STRING")

        if fc.get("monto_solic"):
            add_validation_rule(fc["monto_solic"], "MIN_VALUE", {"limit": 10_000}, "Mínimo $10.000")
            add_validation_rule(fc["monto_solic"], "MAX_VALUE", {"limit": 5_000_000}, "Máximo $5.000.000")
        if fc.get("plazo"):
            add_validation_rule(fc["plazo"], "MIN_VALUE", {"limit": 3})
            add_validation_rule(fc["plazo"], "MAX_VALUE", {"limit": 60})
        if fc.get("score"):
            add_validation_rule(fc["score"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(fc["score"], "MAX_VALUE", {"limit": 1000})

        create_lead_view(camp_cred, "Solicitudes Pendientes", "TABLE",   "PUBLIC")
        create_lead_view(camp_cred, "Pipeline de Créditos",   "BOARD", "PUBLIC")

        log("    Generando leads créditos...", indent=4)
        lead_ids_cred = []
        for _ in range(400):
            monto    = round(random.randint(20_000, 2_000_000) / 1000) * 1000
            plazo    = random.choice([3, 6, 9, 12, 18, 24, 36, 48])
            ingreso  = round(random.randint(80_000, 800_000) / 1000) * 1000
            cuota_est= round(monto / plazo, 2) if plazo else 0
            rel_exp  = round(cuota_est / ingreso * 100, 1) if ingreso else 0

            vals = [
                {"field_id": fc["nombre"],     "value": fake.first_name()},
                {"field_id": fc["apellido"],   "value": fake.last_name()},
                {"field_id": fc["dni"],        "value": str(random.randint(10_000_000, 45_000_000))},
                {"field_id": fc["fecha_nac"],  "value": fake.date_of_birth(minimum_age=21, maximum_age=70).isoformat()},
                {"field_id": fc["email"],      "value": fake.email()},
                {"field_id": fc["telefono"],   "value": f"+549{random.randint(1100000000,1199999999)}"},
                {"field_id": fc["monto_solic"],"value": monto},
                {"field_id": fc["plazo"],      "value": plazo},
                {"field_id": fc["ingreso"],    "value": ingreso},
            ]
            if fc.get("genero") and items_genero:
                vals.append({"field_id": fc["genero"],    "value": rand_nom_id(items_genero)})
            if fc.get("situacion") and items_situacion:
                vals.append({"field_id": fc["situacion"], "value": rand_nom_id(items_situacion)})
            if fc.get("destino") and items_destino:
                vals.append({"field_id": fc["destino"],   "value": rand_nom_id(items_destino)})
            if fc.get("score") and random.random() > 0.3:
                vals.append({"field_id": fc["score"],     "value": random.randint(300, 950)})

            lid = create_lead(camp_cred, vals)
            if lid:
                lead_ids_cred.append((lid, rel_exp))

                # Check CALCULATED relacion cuota/ingreso
                if random.random() < 0.15:
                    lr = api_get(f"/leads/{lid}", params={"detailed": "false"})
                    if lr.status_code == 200:
                        fvs = lr.json().get("field_values", [])
                        rel_fv = next((fv for fv in fvs if fv.get("field_id") == fc.get("relacion")), None)
                        if rel_fv and rel_fv.get("value"):
                            try:
                                got = float(rel_fv["value"])
                                if abs(got - rel_exp) > 1:
                                    warn_calculated("Relacion Cuota/Ingreso", rel_exp, got)
                            except (ValueError, TypeError):
                                warn_calculated("Relacion Cuota/Ingreso", rel_exp, rel_fv.get("value"))

        comentarios_cred = [
            "Solicitante con buen historial crediticio, priorizar análisis.",
            "Documentación incompleta, se solicitó CUIL y recibos de sueldo.",
            "Veraz con deuda activa en mora, evaluar garantía.",
            "Se aprobó el crédito, enviar contrato para firma.",
            "Cliente refinancia deuda anterior, revisar historial completo.",
            "Llamado sin respuesta, recontactar en 48hs.",
            "Ingreso informal, pedir declaración jurada.",
            "Score muy bajo, derivar a producto con mayor tasa.",
        ]

        for lid, rel_exp in lead_ids_cred:
            steps = random.choices([0, 1, 2, 3, 4], weights=[20, 25, 25, 20, 10])[0]
            if steps > 0 and transitions:
                advance_lead_through_flow(lid, transitions, steps)
            if random.random() > 0.5:
                add_comment(lid, random.choice(comentarios_cred))
            # Actualizar monto aprobado en algunos
            if random.random() > 0.6 and fc.get("aprobado"):
                update_lead_fields(lid, camp_cred, [
                    {"field_id": fc["aprobado"], "value": round(random.randint(10_000, 1_500_000) / 1000) * 1000}
                ])

        for lid, _ in random.sample(lead_ids_cred, min(10, len(lead_ids_cred))):
            delete_lead(lid)

        log(f"    {len(lead_ids_cred)} leads crédito generados", indent=4)

    log(f"Organización FINTECH completada ✓", indent=2)


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 4  ███████████████████████
# Concesionaria de Autos — volumen MEDIO (80 leads)
# ===========================================================================
def build_org_concesionaria():
    log("ORGANIZACIÓN 4: Concesionaria de Autos", "STEP")

    org_id = create_organization(
        "AutoElite Mendoza",
        "Concesionaria oficial de vehículos 0km y usados seleccionados."
    )
    if not org_id:
        return
    set_tenant(org_id)
    log(f"Org creada ID={org_id}", indent=2)

    users = []
    for name, email in [
        ("Carlos Mendivil",  "cmendivil@autoelite.com"),
        ("Laura Sosa",       "lsosa@autoelite.com"),
        ("Pablo Morales",    "pmorales@autoelite.com"),
    ]:
        uid = create_user(name, email, org_id)
        if uid:
            users.append(uid)

    items_marca, nom_marca = get_or_create_org_nomenclator(
        "Marca de Vehículo",
        ["Toyota", "Ford", "Chevrolet", "Volkswagen", "Peugeot", "Renault",
         "Fiat", "Honda", "Nissan", "Jeep", "Dodge", "BMW", "Mercedes-Benz"]
    )
    items_tipo_veh, nom_tipo_veh = get_or_create_org_nomenclator(
        "Tipo de Vehículo",
        ["Sedán", "SUV", "Pick-up", "Hatchback", "Coupé", "Furgón", "Familiar", "Deportivo"]
    )
    items_comb, nom_comb = get_or_create_org_nomenclator(
        "Combustible",
        ["Nafta", "Diesel", "Híbrido", "Eléctrico", "GNC", "Nafta/GNC"]
    )
    items_fin_veh, nom_fin_veh = get_or_create_org_nomenclator(
        "Financiación",
        ["Contado", "Crédito Banco Nación", "Crédito Banco Provincia", "Plan de Ahorro",
         "Leasing", "Tarjeta de Crédito"]
    )

    ws_nuevos = create_workspace("Vehículos 0km")
    ws_usados = create_workspace("Vehículos Usados")

    team_ventas_autos = create_team("Ventas Autos",   visibility_shared=True)
    if users:
        add_team_member(team_ventas_autos, users[0], "MANAGER")
        if len(users) > 1: add_team_member(team_ventas_autos, users[1], "AGENT")
        if len(users) > 2: add_team_member(team_ventas_autos, users[2], "AGENT")
    if team_ventas_autos:
        if ws_nuevos: give_team_workspace_access(team_ventas_autos, ws_nuevos)
        if ws_usados: give_team_workspace_access(team_ventas_autos, ws_usados)

    flow_id     = get_default_flow(org_id)
    transitions = get_flow_transitions(flow_id) if flow_id else []

    sec_comp = get_or_create_section("Datos del Comprador")
    sec_veh  = get_or_create_section("Vehículo de Interés")
    sec_neg  = get_or_create_section("Negociación")

    def setup_camp_autos(camp_id, tipo: str) -> dict:
        fa = {}
        fa["nombre"]   = create_field(camp_id, sec_comp, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        fa["apellido"] = create_field(camp_id, sec_comp, template_code="LAST_NAME",  required=True, title_order=2)
        fa["dni"]      = create_field(camp_id, sec_comp, template_code="DNI_ARG",     required=True, is_primary=True)
        fa["email"]    = create_field(camp_id, sec_comp, name="Email",    type_code="STRING", subtype_code="EMAIL", required=True)
        fa["telefono"] = create_field(camp_id, sec_comp, name="Teléfono", type_code="STRING",  subtype_code="MOBILE", required=True)
        fa["marca"]    = create_field(camp_id, sec_veh,  name="Marca",    type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_marca)
        fa["tipo_veh"] = create_field(camp_id, sec_veh,  name="Tipo de Vehículo",
                                       type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_tipo_veh)
        fa["comb"]     = create_field(camp_id, sec_veh,  name="Combustible",
                                       type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_comb)
        fa["color_pref"]=create_field(camp_id, sec_veh,  name="Color Preferido",  type_code="STRING")
        fa["presup"]   = create_field(camp_id, sec_veh,  name="Presupuesto (USD)", type_code="NUMBER", subtype_code="MONEY")
        fa["fin"]      = create_field(camp_id, sec_neg,  name="Forma de Financiación",
                                       type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_fin_veh)
        fa["entrega"]  = create_field(camp_id, sec_neg,  name="Fecha Estimada de Entrega", type_code="DATE")
        fa["descuento"]= create_field(camp_id, sec_neg,  name="Descuento Ofrecido (%)",    type_code="NUMBER", subtype_code="PERCENTAGE")
        fa["precio_final"]=create_field(camp_id, sec_neg, name="Precio Final (USD)",       type_code="NUMBER", subtype_code="MONEY")
        fa["margen"]   = create_field(camp_id, sec_neg,  name="Margen Bruto (%)",          type_code="CALCULATED",
                                       expression='IF({Presupuesto (USD)} > 0, ROUND((1 - ({Precio Final (USD)} / {Presupuesto (USD)})) * 100, 1), 0)')
        fa["satisf"]   = create_field(camp_id, sec_neg,  name="Satisfacción del Cliente",  type_code="NUMBER", subtype_code="STAR_RATING")
        fa["notas"]    = create_field(camp_id, sec_neg,  name="Notas del Vendedor",         type_code="STRING")
        if tipo == "usado":
            fa["km"]   = create_field(camp_id, sec_veh, name="Kilometraje Máximo (km)", type_code="INT")
            fa["anio"] = create_field(camp_id, sec_veh, name="Año Mínimo Fabricación",  type_code="INT")
            if fa.get("anio"):
                add_validation_rule(fa["anio"], "MIN_VALUE", {"limit": 2005})
                add_validation_rule(fa["anio"], "MAX_VALUE", {"limit": 2024})

        if fa.get("descuento"):
            add_validation_rule(fa["descuento"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(fa["descuento"], "MAX_VALUE", {"limit": 30}, "Descuento máximo 30%")
        if fa.get("satisf"):
            add_validation_rule(fa["satisf"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(fa["satisf"], "MAX_VALUE", {"limit": 5})
        return fa

    def gen_leads_autos(camp_id, fa, n, tipo):
        lids = []
        for _ in range(n):
            presup   = random.randint(12_000, 80_000)
            descuento= round(random.uniform(0, 15), 1)
            precio_f = round(presup * (1 - descuento / 100), 2)
            vals = [
                {"field_id": fa["nombre"],   "value": fake.first_name()},
                {"field_id": fa["apellido"], "value": fake.last_name()},
                {"field_id": fa["dni"],      "value": str(random.randint(10_000_000,45_000_000))},
                {"field_id": fa["email"],    "value": fake.email()},
                {"field_id": fa["telefono"], "value": f"+549{random.randint(1100000000,1199999999)}"},
                {"field_id": fa["presup"],   "value": presup},
                {"field_id": fa["descuento"],"value": descuento},
                {"field_id": fa["precio_final"], "value": precio_f},
            ]
            if fa.get("marca") and items_marca:
                vals.append({"field_id": fa["marca"],   "value": rand_nom_id(items_marca)})
            if fa.get("tipo_veh") and items_tipo_veh:
                vals.append({"field_id": fa["tipo_veh"],"value": rand_nom_id(items_tipo_veh)})
            if fa.get("comb") and items_comb:
                vals.append({"field_id": fa["comb"],    "value": rand_nom_id(items_comb)})
            if fa.get("fin") and items_fin_veh:
                vals.append({"field_id": fa["fin"],     "value": rand_nom_id(items_fin_veh)})
            if fa.get("color_pref") and random.random() > 0.4:
                vals.append({"field_id": fa["color_pref"], "value": random.choice(["Blanco","Negro","Gris","Rojo","Azul","Plata","Verde"])})
            if fa.get("entrega") and random.random() > 0.5:
                fut = date.today() + timedelta(days=random.randint(7, 90))
                vals.append({"field_id": fa["entrega"], "value": fut.isoformat()})
            if fa.get("satisf") and random.random() > 0.5:
                vals.append({"field_id": fa["satisf"],  "value": random.randint(1,5)})
            if tipo == "usado":
                if fa.get("km"):
                    vals.append({"field_id": fa["km"],  "value": random.randint(0, 200_000)})
                if fa.get("anio"):
                    vals.append({"field_id": fa["anio"],"value": random.randint(2010, 2023)})
            lid = create_lead(camp_id, vals)
            if lid:
                lids.append(lid)
        return lids

    log("  Campaña: Vehículos 0km", "INFO")
    camp_nuevos = create_campaign("Consultas 0km",     ws_nuevos)
    fa_n = setup_camp_autos(camp_nuevos, "nuevo") if camp_nuevos else {}
    create_lead_view(camp_nuevos, "Pipeline 0km", "BOARD", "PUBLIC") if camp_nuevos else None
    if team_ventas_autos and camp_nuevos:
        give_team_campaign_access(team_ventas_autos, camp_nuevos)
    lid_nuevos = gen_leads_autos(camp_nuevos, fa_n, 50, "nuevo") if camp_nuevos and fa_n else []

    log("  Campaña: Vehículos Usados", "INFO")
    camp_usados = create_campaign("Consultas Usados",  ws_usados)
    fa_u = setup_camp_autos(camp_usados, "usado")  if camp_usados else {}
    create_lead_view(camp_usados, "Pipeline Usados", "BOARD", "PUBLIC") if camp_usados else None
    if team_ventas_autos and camp_usados:
        give_team_campaign_access(team_ventas_autos, camp_usados)
    lid_usados = gen_leads_autos(camp_usados, fa_u, 30, "usado")  if camp_usados and fa_u else []

    comentarios_auto = [
        "Cliente interesado en el modelo Hilux 4x4. Hacer prueba de manejo.",
        "Financiación aprobada, coordinar entrega.",
        "Solicita descuento adicional, consultar con gerencia.",
        "Test drive realizado, cliente muy satisfecho.",
        "Pide cotización con y sin seguro incluido.",
        "Ya tiene otro vehículo para entregar como parte de pago.",
    ]
    for lid in lid_nuevos + lid_usados:
        steps = random.choices([0,1,2,3], weights=[20,35,30,15])[0]
        if steps > 0 and transitions:
            advance_lead_through_flow(lid, transitions, steps)
        if random.random() > 0.5:
            add_comment(lid, random.choice(comentarios_auto))

    for lid in random.sample(lid_nuevos + lid_usados, min(5, len(lid_nuevos + lid_usados))):
        delete_lead(lid)

    log(f"  {len(lid_nuevos)+len(lid_usados)} leads autos generados", indent=2)
    log(f"Organización CONCESIONARIA completada ✓", indent=2)


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 5  ███████████████████████
# Agencia de Marketing B2B — volumen MEDIO-BAJO (40 leads)
# Incluye campos de tipo LEAD (relación entre leads) y type_company
# ===========================================================================
def build_org_marketing_b2b():
    log("ORGANIZACIÓN 5: Agencia Marketing B2B (bajo volumen)", "STEP")

    org_id = create_organization(
        "DigitalBoost Agency",
        "Agencia de marketing digital especializada en generación de leads B2B y performance."
    )
    if not org_id:
        return
    set_tenant(org_id)
    log(f"Org creada ID={org_id}", indent=2)

    users = []
    for name, email in [
        ("Fernanda Acosta",   "facosta@digitalboost.com"),
        ("Ricardo Velázquez", "rvelazquez@digitalboost.com"),
        ("Jimena Paredes",    "jparedes@digitalboost.com"),
    ]:
        uid = create_user(name, email, org_id)
        if uid:
            users.append(uid)

    # Nomencladores
    items_rubro, nom_rubro = get_or_create_org_nomenclator(
        "Rubro de la Empresa",
        ["Tecnología", "Agro", "Fintech", "Logística", "Retail", "Salud", "Educación",
         "Construcción", "Turismo", "Servicios Profesionales", "Industria", "Comercio"]
    )
    items_tipo_empresa, nom_tipo_empresa = get_or_create_org_nomenclator(
        "Tipo de Empresa",
        ["S.A.", "S.R.L.", "Monotributista", "Cooperativa", "ONG", "Fundación",
         "Sociedad de Hecho", "Unipersonal", "S.A.S."]
    )
    items_servicio, nom_servicio = get_or_create_org_nomenclator(
        "Servicio Contratado",
        ["SEO/SEM", "Social Media Management", "Email Marketing", "Diseño Gráfico",
         "Desarrollo Web", "CRM Setup", "Consultoría Estratégica", "Campañas Pagas", "Branding"]
    )
    items_paises, _ = get_global_nomenclator("Países")

    ws_b2b = create_workspace("Clientes B2B", "Empresas que contratan servicios de marketing")

    team_account = create_team("Account Managers", visibility_shared=True)
    if users:
        add_team_member(team_account, users[0], "MANAGER")
        if len(users) > 1: add_team_member(team_account, users[1], "AGENT")
        if len(users) > 2: add_team_member(team_account, users[2], "AGENT")
    if team_account and ws_b2b:
        give_team_workspace_access(team_account, ws_b2b)

    flow_id     = get_default_flow(org_id)
    transitions = get_flow_transitions(flow_id) if flow_id else []

    sec_empresa  = get_or_create_section("Datos de la Empresa")
    sec_contacto = get_or_create_section("Contacto Principal")
    sec_prop     = get_or_create_section("Propuesta Comercial")

    # CAMPAÑA: Prospectos B2B
    log("  Campaña: Prospectos B2B", "INFO")
    camp_b2b = create_campaign("Prospectos Empresas", ws_b2b)
    if team_account and camp_b2b:
        give_team_campaign_access(team_account, camp_b2b)

    fb = {}
    if camp_b2b:
        fb["razon_social"] = create_field(camp_b2b, sec_empresa, name="Razón Social",     type_code="STRING",  required=True, is_primary=True, title_order=1)
        fb["cuit"]         = create_field(camp_b2b, sec_empresa, template_code="CUIT_CUIL", required=True, is_primary=True)
        fb["tipo_empresa"] = create_field(camp_b2b, sec_empresa, name="Tipo de Empresa",
                                           type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_tipo_empresa)
        fb["rubro"]        = create_field(camp_b2b, sec_empresa, name="Rubro",
                                           type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_rubro)
        fb["empleados"]    = create_field(camp_b2b, sec_empresa, name="Cantidad de Empleados", type_code="INT")
        fb["website"]      = create_field(camp_b2b, sec_empresa, name="Sitio Web",             type_code="STRING",  subtype_code="WEBSITE")
        _, _pnom = get_global_nomenclator("Países")
        fb["pais"]         = create_field(camp_b2b, sec_empresa, name="País",
                                           type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=_pnom)

        fb["contacto_nombre"] = create_field(camp_b2b, sec_contacto, template_code="FIRST_NAME", required=True, title_order=2)
        fb["contacto_cargo"]  = create_field(camp_b2b, sec_contacto, name="Cargo del Contacto", type_code="STRING")
        fb["email"]           = create_field(camp_b2b, sec_contacto, name="Email",    type_code="STRING", subtype_code="EMAIL", required=True)
        fb["telefono"]        = create_field(camp_b2b, sec_contacto, name="Teléfono", type_code="STRING",  subtype_code="MOBILE")
        fb["linkedin"]        = create_field(camp_b2b, sec_contacto, name="LinkedIn", type_code="STRING",    subtype_code="SOCIAL_MEDIA")

        fb["servicios"]    = create_field(camp_b2b, sec_prop, name="Servicios de Interés",
                                           type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_servicio)
        fb["presup_mens"]  = create_field(camp_b2b, sec_prop, name="Presupuesto Mensual (USD)", type_code="NUMBER", subtype_code="MONEY")
        fb["contrato_meses"]=create_field(camp_b2b, sec_prop, name="Duración del Contrato (meses)", type_code="INT")
        fb["valor_contrato"]= create_field(camp_b2b, sec_prop, name="Valor Total del Contrato (USD)", type_code="CALCULATED",
                                            expression='{Presupuesto Mensual (USD)} * {Duración del Contrato (meses)}')
        fb["prox_reunion"]  = create_field(camp_b2b, sec_prop, name="Próxima Reunión",    type_code="DATE_TIME", subtype_code="DATE_EVENT")
        fb["propuesta_file"]= create_field(camp_b2b, sec_prop, name="Propuesta Comercial",type_code="FILE",  subtype_code="FILE_DOCUMENT")
        fb["nps"]           = create_field(camp_b2b, sec_prop, name="NPS del Cliente",    type_code="NUMBER",subtype_code="NPS")
        fb["notas"]         = create_field(camp_b2b, sec_prop, name="Notas Internas",     type_code="STRING")

        if fb.get("empleados"):
            add_validation_rule(fb["empleados"], "MIN_VALUE", {"limit": 1})
        if fb.get("contrato_meses"):
            add_validation_rule(fb["contrato_meses"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(fb["contrato_meses"], "MAX_VALUE", {"limit": 36})
        if fb.get("nps"):
            add_validation_rule(fb["nps"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(fb["nps"], "MAX_VALUE", {"limit": 10})

        create_lead_view(camp_b2b, "Pipeline B2B", "BOARD", "PUBLIC")

        log("    Generando leads B2B...", indent=4)
        lead_ids_b2b = []
        for _ in range(40):
            pres_mens = random.randint(500, 10_000)
            meses     = random.choice([3, 6, 9, 12, 18, 24])
            vals = [
                {"field_id": fb["razon_social"],  "value": f"{fake.company()} {random.choice(['S.A.','S.R.L.','S.A.S.'])}"},
                {"field_id": fb["cuit"],           "value": f"30-{fake.numerify('########')}-9"},
                {"field_id": fb["contacto_nombre"],"value": fake.first_name()},
                {"field_id": fb["email"],          "value": fake.company_email()},
                {"field_id": fb["presup_mens"],    "value": pres_mens},
                {"field_id": fb["contrato_meses"], "value": meses},
            ]
            if fb.get("tipo_empresa") and items_tipo_empresa:
                vals.append({"field_id": fb["tipo_empresa"],"value": rand_nom_id(items_tipo_empresa)})
            if fb.get("rubro") and items_rubro:
                vals.append({"field_id": fb["rubro"],       "value": rand_nom_ids(items_rubro, 2)})
            if fb.get("servicios") and items_servicio:
                vals.append({"field_id": fb["servicios"],   "value": rand_nom_ids(items_servicio, 3)})
            if fb.get("empleados") and random.random() > 0.3:
                vals.append({"field_id": fb["empleados"],   "value": random.randint(5, 500)})
            if fb.get("telefono") and random.random() > 0.3:
                vals.append({"field_id": fb["telefono"],    "value": f"+54911{random.randint(10000000,99999999)}"})
            if fb.get("pais") and items_paises:
                vals.append({"field_id": fb["pais"],        "value": rand_nom_id(items_paises)})
            if fb.get("website") and random.random() > 0.4:
                vals.append({"field_id": fb["website"],     "value": f"https://www.{fake.domain_name()}"})
            if fb.get("linkedin") and random.random() > 0.5:
                vals.append({"field_id": fb["linkedin"],    "value": f"https://linkedin.com/company/{fake.user_name()}"})
            if fb.get("nps") and random.random() > 0.5:
                vals.append({"field_id": fb["nps"],         "value": random.randint(0, 10)})
            prox = datetime.now() + timedelta(days=random.randint(1, 30), hours=random.randint(9, 17))
            if fb.get("prox_reunion") and random.random() > 0.4:
                vals.append({"field_id": fb["prox_reunion"],"value": prox.strftime("%Y-%m-%d %H:%M:%S")})

            lid = create_lead(camp_b2b, vals)
            if lid:
                lead_ids_b2b.append(lid)

        comentarios_b2b = [
            "Empresa con presupuesto confirmado para Q1. Alta prioridad.",
            "Contacto pide demo personalizada de la plataforma.",
            "Competidor activo con otra agencia, presionar en diferenciación.",
            "Firmaron NDA, avanzar con propuesta técnica detallada.",
            "Solicitan caso de éxito del mismo rubro.",
            "Presupuesto más bajo de lo esperado, ajustar propuesta.",
            "Reunion excelente, están listos para firmar contrato.",
            "Sin respuesta hace 10 días, enviar follow-up por email.",
        ]
        for lid in lead_ids_b2b:
            steps = random.choices([0,1,2,3,4], weights=[15,25,25,20,15])[0]
            if steps > 0 and transitions:
                advance_lead_through_flow(lid, transitions, steps)
            if random.random() > 0.4:
                add_comment(lid, random.choice(comentarios_b2b))
            if random.random() > 0.6 and fb.get("nps"):
                update_lead_fields(lid, camp_b2b, [{"field_id": fb["nps"], "value": random.randint(5, 10)}])

        for lid in random.sample(lead_ids_b2b, min(3, len(lead_ids_b2b))):
            delete_lead(lid)

        log(f"    {len(lead_ids_b2b)} leads B2B generados", indent=4)

    log(f"Organización MARKETING B2B completada ✓", indent=2)


# ===========================================================================
# MAIN
# ===========================================================================
def run():
    print()
    print("=" * 65)
    print("  🚀  SEED DATA v2 — CRM Multi-Tenant")
    print("=" * 65)
    start = time.time()

    login()
    build_org_salud()
    #print()
    #build_org_inmobiliaria()
    #print()
    #build_org_fintech()
    #print()
    #build_org_concesionaria()
    #print()
    #build_org_marketing_b2b()
    #print()

    elapsed = round(time.time() - start, 1)
    print("=" * 65)
    print(f"  ✅  SEED completado en {elapsed}s")
    if _calc_warnings:
        print(f"  ⚠️   {len(_calc_warnings)} warning(s) de campos CALCULATED emitidos")
    print("=" * 65)

if __name__ == "__main__":
    run()
