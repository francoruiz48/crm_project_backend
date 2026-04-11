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
from datetime import datetime, timedelta, date
from faker import Faker

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8000"
LOCALE    = "es_AR"
fake      = Faker(LOCALE)

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

    r = api_get("/nomenclators", params={"search": name, "global_nomenclator": "true", "page_size": 50})
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

def create_campaign(name: str, workspace_id: int, lead_flow_id: int = None) -> int | None:
    payload = {"name": name, "workspace_id": workspace_id, "active": True}
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
    r = api_get("/lead_state_transitions", params={"lead_flow_id": flow_id, "page_size": 200})
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
def create_user(name: str, email: str) -> int | None:
    r = api_post("/users/", {"name": name, "email": email})
    if r.status_code in (200, 201):
        return r.json()["id"]
    # Si ya existe, buscarlo
    r2 = api_get("/users", params={"search": email, "page_size": 5})
    if r2.status_code == 200:
        items = r2.json().get("items", [])
        match = next((u for u in items if u["email"] == email), None)
        if match:
            return match["id"]
    return None

def get_or_create_org_role(org_id: int) -> int | None:
    """Obtiene el rol admin global (organization_id=NULL) para asignar a usuarios."""
    r = api_get("/roles", params={"page_size": 50})
    if r.status_code == 200:
        for role in r.json().get("items", []):
            if role.get("code") == "admin" and role.get("organization_id") is None:
                return role["id"]
    return None

def assign_user_to_org(user_id: int, org_id: int):
    """Promueve un usuario como owner de la org (esto crea el UserOrganization)."""
    api_put(f"/users/organization/{org_id}/promote-owner/{user_id}", {})

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
def create_lead(campaign_id: int, values: list[dict]) -> int | None:
    clean = [v for v in values if v.get("field_id") is not None and v.get("value") is not None]
    r = api_post("/leads/", {"campaign_id": campaign_id, "values": clean})
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
    # Primero obtenemos el estado actual del lead
    r = api_get(f"/leads/{lead_id}", params={"detailed": "false"})
    if r.status_code != 200:
        return
    current_state_id = r.json().get("current_state_id")
    if not current_state_id:
        return

    steps_done = 0
    for _ in range(target_steps):
        # Buscar transiciones válidas desde el estado actual
        valid_next = [t for t in transitions if t["from_state_id"] == current_state_id]
        if not valid_next:
            break
        chosen = random.choice(valid_next)
        new_state_id = chosen["to_state_id"]
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
def create_lead_view(campaign_id: int, name: str, view_type: str = "LIST", visibility: str = "PUBLIC"):
    api_post("/lead_views/", {
        "campaign_id": campaign_id,
        "name": name,
        "visibility": visibility,
        "view_type": view_type,
        "filters": {},
        "ui_config": {},
        "sort_config": {"sort_by": "created_at", "ascending": False}
    })


# ---------------------------------------------------------------------------
# HELPERS: ROUTING RULES
# ---------------------------------------------------------------------------
def create_routing_rule(campaign_id: int, condition_type: str, condition_target_id: int,
                         condition_value: str, target_team_id: int, order: int):
    api_post("/lead_routing_rules/", {
        "campaign_id": campaign_id,
        "condition_type": condition_type,
        "condition_target_id": condition_target_id,
        "condition_value": str(condition_value),
        "target_team_id": target_team_id,
        "order": order,
    })


# ===========================================================================
# ███████████████████████  ORGANIZACIÓN 1  ███████████████████████
# Clínica y Salud — volumen medio (60 leads)
# Flujo DEFAULT, flujo PERSONALIZADO para una campaña premium
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

    # --- Usuarios ---
    users = []
    for name, email in [
        ("Valentina Suárez",   "vsuarez@medicare.com"),
        ("Rodrigo Fernández",  "rfernandez@medicare.com"),
        ("Camila Torres",      "ctorres@medicare.com"),
    ]:
        uid = create_user(name, email)
        if uid:
            assign_user_to_org(uid, org_id)
            users.append(uid)
    log(f"Usuarios creados: {len(users)}", indent=2)

    # --- Nomencladores de organización ---
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
    items_paises, _  = get_global_nomenclator("Países")
    items_prov, _    = get_global_nomenclator("Provincias")

    # --- Workspaces ---
    ws_pacientes = create_workspace("Pacientes Generales", "Gestión de pacientes ambulatorios")
    ws_estetica  = create_workspace("Medicina Estética",   "Tratamientos estéticos y cirugías menores")

    # --- Equipos ---
    team_admision = create_team("Admisión y Recepción", visibility_shared=True)
    team_medicos  = create_team("Equipo Médico",         visibility_shared=False)
    if team_admision and users:
        add_team_member(team_admision, users[0], "MANAGER")
        if len(users) > 1:
            add_team_member(team_admision, users[1], "AGENT")
    if team_medicos and len(users) > 2:
        add_team_member(team_medicos, users[2], "MANAGER")

    # Dar acceso al workspace
    if team_admision and ws_pacientes:
        give_team_workspace_access(team_admision, ws_pacientes)
    if team_medicos and ws_estetica:
        give_team_workspace_access(team_medicos, ws_estetica)

    flow_id = get_default_flow(org_id)
    transitions = get_flow_transitions(flow_id) if flow_id else []
    states       = get_flow_states(flow_id)      if flow_id else []
    # Estado inicial
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
    # CAMPAÑA 1: Pacientes Clínica General
    # -----------------------------------------------------------------------
    log("  Campaña: Pacientes Clínica General", "INFO")
    camp_pacientes = create_campaign("Pacientes Clínica General", ws_pacientes)
    if team_admision and camp_pacientes:
        give_team_campaign_access(team_admision, camp_pacientes)

    sec_personal  = get_or_create_section("Datos Personales")
    sec_medico    = get_or_create_section("Datos Médicos")
    sec_adicional = get_or_create_section("Información Adicional")

    f = {}
    if camp_pacientes:
        f["nombre"]       = create_field(camp_pacientes, sec_personal, template_code="FIRST_NAME",   required=True,  is_primary=True, title_order=1)
        f["apellido"]     = create_field(camp_pacientes, sec_personal, template_code="LAST_NAME",    required=True,  is_primary=True, title_order=2)
        f["dni"]          = create_field(camp_pacientes, sec_personal, template_code="DNI_ARG",       required=True,  is_primary=True)
        f["fecha_nac"]    = create_field(camp_pacientes, sec_personal, template_code="BIRTH_DATE",    required=True)
        _, _gnom = get_global_nomenclator("Genero")
        f["genero"]       = create_field(camp_pacientes, sec_personal, name="Género", type_code="SELECTOR",
                                          subtype_code="SELECTOR_SIMPLE", nom_id=_gnom)
        f["email"]        = create_field(camp_pacientes, sec_personal, name="Email",   type_code="EMAIL",  required=True)
        f["telefono"]     = create_field(camp_pacientes, sec_personal, name="Teléfono",type_code="PHONE",  subtype_code="MOBILE")

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

        # Reglas extra en peso y altura
        if f.get("peso"):
            add_validation_rule(f["peso"],   "MIN_VALUE", {"limit": 20}, "El peso mínimo es 20 kg.")
            add_validation_rule(f["peso"],   "MAX_VALUE", {"limit": 300}, "El peso máximo es 300 kg.")
        if f.get("altura"):
            add_validation_rule(f["altura"], "MIN_VALUE", {"limit": 0.5}, "La altura mínima es 0.5 m.")
            add_validation_rule(f["altura"], "MAX_VALUE", {"limit": 2.5},  "La altura máxima es 2.5 m.")

        create_lead_view(camp_pacientes, "Todos los Pacientes",       "LIST",   "PUBLIC")
        create_lead_view(camp_pacientes, "Kanban por Estado",         "KANBAN", "PUBLIC")

        # --- Generar leads ---
        log("    Generando leads pacientes...", indent=4)
        items_os_c, _ = get_or_create_campaign_nomenclator("Cobertura Médica",
            ["OSDE", "Swiss Medical", "Galeno", "PAMI", "Particular", "Sancor Salud"], camp_pacientes)
        _, _gnom = get_global_nomenclator("Genero")
        items_g, _   = get_global_nomenclator("Genero")

        lead_ids_pac = []
        for i in range(50):
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
            if f.get("obra_social") and items_os_c:
                vals.append({"field_id": f["obra_social"], "value": rand_nom_id(items_os_c)})
            if f.get("telefono") and random.random() > 0.2:
                vals.append({"field_id": f["telefono"],    "value": f"+549{random.randint(1100000000,1199999999)}"})
            if f.get("tension") and random.random() > 0.4:
                vals.append({"field_id": f["tension"],     "value": f"{random.randint(100,140)}/{random.randint(60,90)}"})
            if f.get("prox_turno") and random.random() > 0.5:
                vals.append({"field_id": f["prox_turno"],  "value": futuro.strftime("%Y-%m-%d %H:%M:%S")})

            lid = create_lead(camp_pacientes, vals)
            if lid:
                lead_ids_pac.append((lid, imc_exp))

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

        # Avanzar estados y agregar comentarios
        for idx, (lid, _) in enumerate(lead_ids_pac):
            steps = random.choices([0, 1, 2, 3, 4], weights=[15, 30, 25, 20, 10])[0]
            if steps > 0 and transitions:
                advance_lead_through_flow(lid, transitions, steps)

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

    # -----------------------------------------------------------------------
    # CAMPAÑA 2: Medicina Estética (flujo personalizado)
    # -----------------------------------------------------------------------
    log("  Campaña: Medicina Estética", "INFO")
    camp_estetica = create_campaign("Consultas Estética", ws_estetica, lead_flow_id=flow_estetica_id)
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
    if camp_estetica:
        fe["nombre"]      = create_field(camp_estetica, sec_est_1, template_code="FIRST_NAME", required=True, is_primary=True, title_order=1)
        fe["apellido"]    = create_field(camp_estetica, sec_est_1, template_code="LAST_NAME",  required=True, title_order=2)
        fe["email"]       = create_field(camp_estetica, sec_est_1, name="Email",    type_code="EMAIL",  required=True, is_primary=True)
        fe["telefono"]    = create_field(camp_estetica, sec_est_1, name="Teléfono", type_code="PHONE",  subtype_code="MOBILE", required=True)
        fe["edad"]        = create_field(camp_estetica, sec_est_1, template_code="AGE")
        fe["instagram"]   = create_field(camp_estetica, sec_est_1, template_code="INSTAGRAM_USER")
        fe["tratamiento"] = create_field(camp_estetica, sec_est_2, name="Tratamiento Solicitado",
                                          type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_trat)
        fe["zona"]        = create_field(camp_estetica, sec_est_2, name="Zona a Tratar",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_zona)
        fe["presupuesto"] = create_field(camp_estetica, sec_est_2, name="Presupuesto Aprobado (USD)", type_code="MONEY")
        fe["fecha_trat"]  = create_field(camp_estetica, sec_est_2, name="Fecha Tratamiento",          type_code="DATE_TIME")
        fe["sesiones"]    = create_field(camp_estetica, sec_est_2, name="Nro Sesiones",                type_code="INT",    default_value="1")
        fe["costo_ses"]   = create_field(camp_estetica, sec_est_2, name="Costo por Sesión (USD)",      type_code="MONEY")
        fe["costo_total"] = create_field(camp_estetica, sec_est_2, name="Costo Total (USD)",           type_code="CALCULATED",
                                          expression='{Nro Sesiones} * {Costo por Sesión (USD)}')
        fe["satisfaccion"]= create_field(camp_estetica, sec_est_3, name="Satisfacción",               type_code="RATING",  subtype_code="STAR_RATING")
        fe["notas_post"]  = create_field(camp_estetica, sec_est_3, name="Notas Post-Tratamiento",      type_code="STRING")
        fe["foto_antes"]  = create_field(camp_estetica, sec_est_3, name="Foto Antes",                  type_code="FILE",   subtype_code="FILE_IMAGE", is_visible=True)

        if fe.get("presupuesto"):
            add_validation_rule(fe["presupuesto"], "MIN_VALUE", {"limit": 0})
        if fe.get("sesiones"):
            add_validation_rule(fe["sesiones"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(fe["sesiones"], "MAX_VALUE", {"limit": 20})

        create_lead_view(camp_estetica, "Pipeline Estética", "KANBAN", "PUBLIC")

        # Generar leads
        log("    Generando leads estética...", indent=4)
        lead_ids_est = []
        for _ in range(30):
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

            lid = create_lead(camp_estetica, vals)
            if lid:
                lead_ids_est.append((lid, costo_tot_exp))

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
            steps = random.choices([0, 1, 2, 3, 4, 5], weights=[10, 20, 20, 20, 15, 15])[0]
            if steps > 0 and transitions_estetica:
                advance_lead_through_flow(lid, transitions_estetica, steps)
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
        uid = create_user(name, email)
        if uid:
            assign_user_to_org(uid, org_id)
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
    items_paises, _ = get_global_nomenclator("Países")
    items_prov, _   = get_global_nomenclator("Provincias")

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
        flds["email"]      = create_field(camp_id, sec_contacto, name="Email",    type_code="EMAIL",  required=True, is_primary=True)
        flds["telefono"]   = create_field(camp_id, sec_contacto, name="Teléfono", type_code="PHONE",  subtype_code="MOBILE", required=True)
        flds["whatsapp"]   = create_field(camp_id, sec_contacto, name="WhatsApp", type_code="PHONE",  subtype_code="WHATSAPP")
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
            flds["presup_usd"]  = create_field(camp_id, sec_finanzas, name="Presupuesto (USD)",     type_code="MONEY")
            flds["financiado"]  = create_field(camp_id, sec_finanzas, name="Busca Financiamiento",  type_code="BOOL", default_value="false")
            flds["cuotas"]      = create_field(camp_id, sec_finanzas, name="Cuotas Disponibles",    type_code="INT")
            flds["rentabilidad"]= create_field(camp_id, sec_finanzas, name="Rentabilidad Esperada (%)", type_code="CALCULATED",
                                               expression='IF({Presupuesto (USD)} > 0, ROUND(({Presupuesto (USD)} * 0.06), 0), 0)')
        else:
            flds["alquiler_max"]= create_field(camp_id, sec_finanzas, name="Alquiler Máximo (ARS)", type_code="MONEY")
            flds["expensas_max"]= create_field(camp_id, sec_finanzas, name="Expensas Máximas (ARS)",type_code="MONEY")
            flds["total_max"]   = create_field(camp_id, sec_finanzas, name="Total Máximo (ARS)",    type_code="CALCULATED",
                                               expression='{Alquiler Máximo (ARS)} + {Expensas Máximas (ARS)}')

        flds["canal_origen"] = create_field(camp_id, sec_seguimiento, name="Canal de Origen",  type_code="STRING")
        flds["primer_cont"]  = create_field(camp_id, sec_seguimiento, name="Primer Contacto",   type_code="DATE_TIME")
        flds["ult_seguim"]   = create_field(camp_id, sec_seguimiento, name="Último Seguimiento",type_code="DATE_TIME")
        flds["rating_cli"]   = create_field(camp_id, sec_seguimiento, name="Calidad del Lead",  type_code="RATING",  subtype_code="NPS")
        flds["notas"]        = create_field(camp_id, sec_seguimiento, name="Notas Comerciales", type_code="STRING")
        flds["website_ref"]  = create_field(camp_id, sec_seguimiento, name="Sitio Web Referido",type_code="URL",  subtype_code="WEBSITE")

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
    create_lead_view(camp_ventas, "Pipeline Ventas", "KANBAN", "PUBLIC") if camp_ventas else None
    lead_ids_v = gen_leads_inmob(camp_ventas, flds_v, 500, "venta") if camp_ventas and flds_v else []
    log(f"    {len(lead_ids_v)} leads ventas", indent=4)

    # Campaña B: Alquileres
    log("  Campaña: Búsqueda de Alquiler", "INFO")
    camp_alq = create_campaign("Búsqueda de Alquiler", ws_alquileres)
    if team_alq and camp_alq:
        give_team_campaign_access(team_alq, camp_alq)
    flds_a = setup_camp_inmob(camp_alq, "alquiler") if camp_alq else {}
    create_lead_view(camp_alq, "Pipeline Alquileres", "KANBAN", "PUBLIC") if camp_alq else None
    lead_ids_a = gen_leads_inmob(camp_alq, flds_a, 500, "alquiler") if camp_alq and flds_a else []
    log(f"    {len(lead_ids_a)} leads alquileres", indent=4)

    # Campaña C: Inversores
    log("  Campaña: Inversores y Desarrolladores", "INFO")
    camp_inv = create_campaign("Inversores y Desarrolladores", ws_inversores)
    if team_inversores and camp_inv:
        give_team_campaign_access(team_inversores, camp_inv)
    flds_i = setup_camp_inmob(camp_inv, "inversores") if camp_inv else {}
    create_lead_view(camp_inv, "Pipeline Inversores", "LIST", "PUBLIC") if camp_inv else None
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
        uid = create_user(name, email)
        if uid:
            assign_user_to_org(uid, org_id)
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
        fc["email"]       = create_field(camp_cred, sec_sol, name="Email",    type_code="EMAIL",  required=True)
        fc["telefono"]    = create_field(camp_cred, sec_sol, name="Teléfono", type_code="PHONE",  subtype_code="MOBILE", required=True)
        _, _gnom = get_global_nomenclator("Genero")
        fc["genero"]      = create_field(camp_cred, sec_sol, name="Género",   type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=_gnom)
        fc["situacion"]   = create_field(camp_cred, sec_sol, name="Situación Laboral",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_situacion)

        fc["monto_solic"] = create_field(camp_cred, sec_cred, name="Monto Solicitado (ARS)", type_code="MONEY",  required=True)
        fc["plazo"]       = create_field(camp_cred, sec_cred, name="Plazo (meses)",          type_code="INT",    required=True)
        fc["destino"]     = create_field(camp_cred, sec_cred, name="Destino del Crédito",
                                          type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_destino)
        fc["ingreso"]     = create_field(camp_cred, sec_cred, name="Ingreso Mensual (ARS)",  type_code="MONEY")
        fc["relacion"]    = create_field(camp_cred, sec_anal, name="Relación Cuota/Ingreso (%)", type_code="CALCULATED",
                                          expression='IF(AND({Ingreso Mensual (ARS)} > 0, {Plazo (meses)} > 0), ROUND(({Monto Solicitado (ARS)} / {Plazo (meses)}) / {Ingreso Mensual (ARS)} * 100, 1), 0)')
        fc["riesgo"]      = create_field(camp_cred, sec_anal, name="Nivel de Riesgo",         type_code="CALCULATED",
                                          expression='IF({Relación Cuota/Ingreso (%)} = 0, "Sin datos", IF({Relación Cuota/Ingreso (%)} <= 25, "Bajo", IF({Relación Cuota/Ingreso (%)} <= 40, "Medio", "Alto")))')
        fc["score"]       = create_field(camp_cred, sec_anal, name="Score Crediticio",         type_code="INT")
        fc["aprobado"]    = create_field(camp_cred, sec_anal, name="Monto Aprobado (ARS)",     type_code="MONEY")
        fc["tasa"]        = create_field(camp_cred, sec_anal, name="Tasa Aplicada (%)",        type_code="NUMBER")
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

        create_lead_view(camp_cred, "Solicitudes Pendientes", "LIST",   "PUBLIC")
        create_lead_view(camp_cred, "Pipeline de Créditos",   "KANBAN", "PUBLIC")

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
        uid = create_user(name, email)
        if uid:
            assign_user_to_org(uid, org_id)
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
    items_paises, _ = get_global_nomenclator("Países")

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
        fa["email"]    = create_field(camp_id, sec_comp, name="Email",    type_code="EMAIL",  required=True)
        fa["telefono"] = create_field(camp_id, sec_comp, name="Teléfono", type_code="PHONE",  subtype_code="MOBILE", required=True)
        fa["marca"]    = create_field(camp_id, sec_veh,  name="Marca",    type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_marca)
        fa["tipo_veh"] = create_field(camp_id, sec_veh,  name="Tipo de Vehículo",
                                       type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_tipo_veh)
        fa["comb"]     = create_field(camp_id, sec_veh,  name="Combustible",
                                       type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_comb)
        fa["color_pref"]=create_field(camp_id, sec_veh,  name="Color Preferido",  type_code="STRING")
        fa["presup"]   = create_field(camp_id, sec_veh,  name="Presupuesto (USD)", type_code="MONEY")
        fa["fin"]      = create_field(camp_id, sec_neg,  name="Forma de Financiación",
                                       type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=nom_fin_veh)
        fa["entrega"]  = create_field(camp_id, sec_neg,  name="Fecha Estimada de Entrega", type_code="DATE")
        fa["descuento"]= create_field(camp_id, sec_neg,  name="Descuento Ofrecido (%)",    type_code="NUMBER")
        fa["precio_final"]=create_field(camp_id, sec_neg, name="Precio Final (USD)",       type_code="MONEY")
        fa["margen"]   = create_field(camp_id, sec_neg,  name="Margen Bruto (%)",          type_code="CALCULATED",
                                       expression='IF({Presupuesto (USD)} > 0, ROUND((1 - ({Precio Final (USD)} / {Presupuesto (USD)})) * 100, 1), 0)')
        fa["satisf"]   = create_field(camp_id, sec_neg,  name="Satisfacción del Cliente",  type_code="RATING", subtype_code="STAR_RATING")
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
    create_lead_view(camp_nuevos, "Pipeline 0km", "KANBAN", "PUBLIC") if camp_nuevos else None
    if team_ventas_autos and camp_nuevos:
        give_team_campaign_access(team_ventas_autos, camp_nuevos)
    lid_nuevos = gen_leads_autos(camp_nuevos, fa_n, 50, "nuevo") if camp_nuevos and fa_n else []

    log("  Campaña: Vehículos Usados", "INFO")
    camp_usados = create_campaign("Consultas Usados",  ws_usados)
    fa_u = setup_camp_autos(camp_usados, "usado")  if camp_usados else {}
    create_lead_view(camp_usados, "Pipeline Usados", "KANBAN", "PUBLIC") if camp_usados else None
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
        uid = create_user(name, email)
        if uid:
            assign_user_to_org(uid, org_id)
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
        fb["website"]      = create_field(camp_b2b, sec_empresa, name="Sitio Web",             type_code="URL",  subtype_code="WEBSITE")
        _, _pnom = get_global_nomenclator("Países")
        fb["pais"]         = create_field(camp_b2b, sec_empresa, name="País",
                                           type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=_pnom)

        fb["contacto_nombre"] = create_field(camp_b2b, sec_contacto, template_code="FIRST_NAME", required=True, title_order=2)
        fb["contacto_cargo"]  = create_field(camp_b2b, sec_contacto, name="Cargo del Contacto", type_code="STRING")
        fb["email"]           = create_field(camp_b2b, sec_contacto, name="Email",    type_code="EMAIL",  required=True)
        fb["telefono"]        = create_field(camp_b2b, sec_contacto, name="Teléfono", type_code="PHONE",  subtype_code="MOBILE")
        fb["linkedin"]        = create_field(camp_b2b, sec_contacto, name="LinkedIn", type_code="URL",    subtype_code="SOCIAL_MEDIA")

        fb["servicios"]    = create_field(camp_b2b, sec_prop, name="Servicios de Interés",
                                           type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_servicio)
        fb["presup_mens"]  = create_field(camp_b2b, sec_prop, name="Presupuesto Mensual (USD)", type_code="MONEY")
        fb["contrato_meses"]=create_field(camp_b2b, sec_prop, name="Duración del Contrato (meses)", type_code="INT")
        fb["valor_contrato"]= create_field(camp_b2b, sec_prop, name="Valor Total del Contrato (USD)", type_code="CALCULATED",
                                            expression='{Presupuesto Mensual (USD)} * {Duración del Contrato (meses)}')
        fb["prox_reunion"]  = create_field(camp_b2b, sec_prop, name="Próxima Reunión",    type_code="DATE_TIME")
        fb["propuesta_file"]= create_field(camp_b2b, sec_prop, name="Propuesta Comercial",type_code="FILE",  subtype_code="FILE_DOCUMENT")
        fb["nps"]           = create_field(camp_b2b, sec_prop, name="NPS del Cliente",    type_code="RATING",subtype_code="NPS")
        fb["notas"]         = create_field(camp_b2b, sec_prop, name="Notas Internas",     type_code="STRING")

        if fb.get("empleados"):
            add_validation_rule(fb["empleados"], "MIN_VALUE", {"limit": 1})
        if fb.get("contrato_meses"):
            add_validation_rule(fb["contrato_meses"], "MIN_VALUE", {"limit": 1})
            add_validation_rule(fb["contrato_meses"], "MAX_VALUE", {"limit": 36})
        if fb.get("nps"):
            add_validation_rule(fb["nps"], "MIN_VALUE", {"limit": 0})
            add_validation_rule(fb["nps"], "MAX_VALUE", {"limit": 10})

        create_lead_view(camp_b2b, "Pipeline B2B", "KANBAN", "PUBLIC")

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

    build_org_salud()
    print()
    build_org_inmobiliaria()
    print()
    build_org_fintech()
    print()
    build_org_concesionaria()
    print()
    build_org_marketing_b2b()
    print()

    elapsed = round(time.time() - start, 1)
    print("=" * 65)
    print(f"  ✅  SEED completado en {elapsed}s")
    if _calc_warnings:
        print(f"  ⚠️   {len(_calc_warnings)} warning(s) de campos CALCULATED emitidos")
    print("=" * 65)

if __name__ == "__main__":
    run()
