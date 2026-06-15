import pytest

# =============================================================================
# FIXTURES DE PREPARACIÓN
# =============================================================================

@pytest.fixture
def flow_setup(api, db_session, initial_structure):
    """
    Prepara un escenario completo:
    - 1 LeadFlow válido con 3 estados (Nuevo -> Contactado -> Ganado)
    - 1 Campaña usando ese flujo
    - 1 LeadFlow vacío (para probar errores)
    """
    ws_id = initial_structure["workspace_id"]

    # 1. Crear Flujos
    res_flow_1 = api.client.post("/lead_flows/", json={"name": "Flujo de Ventas"}, headers=api.headers)
    flow_1_id = res_flow_1.json()["id"]

    res_flow_2 = api.client.post("/lead_flows/", json={"name": "Flujo Vacío"}, headers=api.headers)
    flow_2_id = res_flow_2.json()["id"]

    # 2. Crear Estados en Flujo 1
    s1 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_1_id, "name": "Nuevo", "category": "OPEN", "is_initial": True
    }, headers=api.headers).json()

    s2 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_1_id, "name": "Contactado", "category": "OPEN", "is_initial": False
    }, headers=api.headers).json()

    s3 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_1_id, "name": "Ganado", "category": "WON", "is_initial": False
    }, headers=api.headers).json()

    # 3. Crear Transiciones (Nuevo -> Contactado -> Ganado)
    api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_1_id, "from_state_id": s1["id"], "to_state_id": s2["id"]
    }, headers=api.headers)

    api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_1_id, "from_state_id": s2["id"], "to_state_id": s3["id"]
    }, headers=api.headers)

    # 4. Crear Campañas
    c1 = api.client.post("/campaigns/", json={
        "name": "Campaña con Flujo", "workspace_id": ws_id, "lead_flow_id": flow_1_id, "active": True
    }, headers=api.headers).json()

    c2 = api.client.post("/campaigns/", json={
        "name": "Campaña sin Flujo", "workspace_id": ws_id, "lead_flow_id": flow_2_id, "active": True
    }, headers=api.headers).json()

    api.client.post("/lead_fields/", json={
        "campaign_id": c1["id"], "name": "Nombre Dummy", "field_type_code": "STRING"
    }, headers=api.headers)

    api.client.post("/lead_fields/", json={
        "campaign_id": c2["id"], "name": "Nombre Dummy", "field_type_code": "STRING"
    }, headers=api.headers)

    return {
        "flow_valid_id": flow_1_id,
        "flow_empty_id": flow_2_id,
        "state_nuevo_id": s1["id"],
        "state_contactado_id": s2["id"],
        "state_ganado_id": s3["id"],
        "camp_valid_id": c1["id"],
        "camp_empty_id": c2["id"],
    }


@pytest.fixture
def bulk_flow_setup(api):
    """
    Prepara un flujo y 3 estados para aislar las pruebas de transiciones masivas.
    """
    f_res = api.client.post("/lead_flows/", json={"name": "Bulk Flow Tests"}, headers=api.headers).json()
    f_id = f_res["id"]

    s1 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "Paso 1", "category": "OPEN", "is_initial": True}, headers=api.headers).json()
    s2 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "Paso 2", "category": "OPEN"}, headers=api.headers).json()
    s3 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "Exito",  "category": "WON"}, headers=api.headers).json()

    return {
        "flow_id": f_id,
        "s1_id": s1["id"],
        "s2_id": s2["id"],
        "s3_id": s3["id"],
    }


@pytest.fixture
def graph_flow_setup(api):
    """
    Fixture exclusivo para tests del Orchestrator (/lead_flows/graph).
    Crea un flujo completo vía API para tener IDs reales disponibles.
    """
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Grafo Base",
        "states": [
            {"id": -1, "name": "Inicio",     "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": -2, "name": "En Proceso", "category": "OPEN", "is_initial": False, "order": 2},
            {"id": -3, "name": "Ganado",     "category": "WON",  "is_initial": False},
        ],
        "transitions": [
            {"from_state_id": -1, "to_state_id": -2},
            {"from_state_id": -2, "to_state_id": -3},
        ]
    }, headers=api.headers)
    assert res.status_code == 200, f"graph_flow_setup falló: {res.text}"
    flow_id = res.json()["id"]

    states = api.client.get(
        f"/lead_states/?lead_flow_id={flow_id}&page_size=10", headers=api.headers
    ).json()["items"]
    state_map = {s["name"]: s["id"] for s in states}

    ws_res = api.client.get("/workspaces/?page_size=1", headers=api.headers).json()["items"]
    ws_id = ws_res[0]["id"]

    camp = api.client.post("/campaigns/", json={
        "name": "Campaña Grafo", "workspace_id": ws_id, "lead_flow_id": flow_id, "active": True
    }, headers=api.headers).json()

    # Campo dummy no requerido para que la creación de leads funcione
    api.client.post("/lead_fields/", json={
        "campaign_id": camp["id"], "name": "Nombre Dummy", "field_type_code": "STRING", "required": False
    }, headers=api.headers)

    return {
        "flow_id":         flow_id,
        "s_inicio_id":     state_map["Inicio"],
        "s_en_proceso_id": state_map["En Proceso"],
        "s_ganado_id":     state_map["Ganado"],
        "camp_id":         camp["id"],
    }


# =============================================================================
# TESTS DE LÓGICA DE ESTADOS (LeadStateService)
# =============================================================================

def test_lead_state_only_one_initial(api, flow_setup):
    """Guerra de estados iniciales: El sistema debe impedir 2 estados initial=True en un flujo."""
    flow_id = flow_setup["flow_valid_id"]

    res = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Otro Inicio", "category": "OPEN", "is_initial": True
    }, headers=api.headers)

    assert res.status_code == 400
    assert "Ya existe un estado inicial" in res.text


def test_lead_state_auto_order_and_won_category(api, flow_setup):
    """
    1. Si no envío order en OPEN, debe autocalcularlo (Max + 1).
    2. Si envío category WON, el order debe forzarse a Null aunque yo envíe un número.
    """
    flow_id = flow_setup["flow_valid_id"]

    # Caso 1: Nuevo estado OPEN (El fixture ya tiene order 1 y 2, este debería ser 3)
    res_open = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Negociación", "category": "OPEN", "is_initial": False
    }, headers=api.headers)
    assert res_open.status_code == 200
    assert res_open.json()["order"] == 3

    # Caso 2: Nuevo estado LOST enviando un order tramposo (Debe ignorar el 99 y poner null)
    res_lost = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Perdido", "category": "LOST", "is_initial": False, "order": 99
    }, headers=api.headers)
    assert res_lost.status_code == 200
    assert res_lost.json()["order"] is None


def test_lead_state_duplicate_order_prevented(api, flow_setup):
    """Evitar colisión de columnas visuales."""
    flow_id = flow_setup["flow_valid_id"]

    res = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Pirata", "category": "OPEN", "order": 1
    }, headers=api.headers)

    assert res.status_code == 400
    assert "ya está en uso" in res.text


# =============================================================================
# TESTS DE VALIDACIÓN: ESTADO INICIAL (nuevas reglas)
# =============================================================================

def test_lead_state_initial_must_be_open_on_create(api, flow_setup):
    """Un estado WON o LOST no puede ser marcado como inicial al crearlo."""
    flow_id = flow_setup["flow_valid_id"]

    res_won = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "WON Inicial", "category": "WON", "is_initial": True
    }, headers=api.headers)
    assert res_won.status_code == 400
    assert "categoría OPEN" in res_won.text

    res_lost = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "LOST Inicial", "category": "LOST", "is_initial": True
    }, headers=api.headers)
    assert res_lost.status_code == 400
    assert "categoría OPEN" in res_lost.text


def test_lead_state_initial_must_be_open_on_update(api, flow_setup):
    """Actualizar un estado WON/LOST a is_initial=True debe ser rechazado."""
    s_ganado = flow_setup["state_ganado_id"]
    s_nuevo  = flow_setup["state_nuevo_id"]

    # Primero desmarcamos el estado inicial actual para que el error sea solo por categoría
    api.client.put(f"/lead_states/{s_nuevo}", json={"is_initial": False}, headers=api.headers)

    res = api.client.put(f"/lead_states/{s_ganado}", json={"is_initial": True}, headers=api.headers)
    assert res.status_code == 400
    assert "categoría OPEN" in res.text


# =============================================================================
# TESTS DE GRAFO DE TRANSICIONES (LeadStateTransitionService)
# =============================================================================

def test_transition_prevent_cross_flow(api, flow_setup):
    """Evitar mezclar estados de Flujo A con estados de Flujo B."""
    f1_state_id = flow_setup["state_nuevo_id"]

    s_f2 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_setup["flow_empty_id"], "name": "Inicio F2", "category": "OPEN"
    }, headers=api.headers).json()

    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_setup["flow_valid_id"],
        "from_state_id": f1_state_id,
        "to_state_id": s_f2["id"],
    }, headers=api.headers)

    assert res.status_code == 400
    assert "no pertenece al flujo" in res.text


def test_transition_prevent_duplicates(api, flow_setup):
    """No se puede registrar dos veces la misma flecha."""
    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_setup["flow_valid_id"],
        "from_state_id": flow_setup["state_nuevo_id"],
        "to_state_id": flow_setup["state_contactado_id"],
    }, headers=api.headers)

    assert res.status_code == 400
    assert "ya existe en el flujo" in res.text


# =============================================================================
# TESTS DEL CICLO DE VIDA DEL LEAD Y EL HISTORIAL
# =============================================================================

def test_create_lead_requires_initial_state(api, flow_setup):
    """Si la campaña usa un flujo vacío (sin estado inicial), no se puede crear el lead."""
    camp_empty = flow_setup["camp_empty_id"]

    res = api.client.post("/leads/", json={"campaign_id": camp_empty, "values": []}, headers=api.headers)

    assert res.status_code == 400
    assert "no tiene un flujo de estados válido" in res.text


def test_lead_lifecycle_and_history(api, flow_setup):
    """
    Simula la vida de un Lead:
    1. Creación (Nace en 'Nuevo' y guarda History 1).
    2. Movimiento Legal (Pasa a 'Contactado' -> Funciona y guarda History 2).
    3. Movimiento Ilegal (Intenta saltar a 'Ganado' directamente -> Falla).
    """
    camp_valid   = flow_setup["camp_valid_id"]
    st_nuevo     = flow_setup["state_nuevo_id"]
    st_contactado = flow_setup["state_contactado_id"]
    st_ganado    = flow_setup["state_ganado_id"]

    # LEAD 1: HAPPY PATH
    res_lead = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    assert res_lead.status_code == 200
    lead_id = res_lead.json()["id"]
    assert res_lead.json()["current_state_id"] == st_nuevo

    # Historial 1 (primer estado, from_state_id debe ser null)
    res_hist_1 = api.client.get(f"/lead_state_history/?lead_id={lead_id}", headers=api.headers).json()["items"]
    assert len(res_hist_1) == 1
    assert res_hist_1[0]["from_state_id"] is None
    assert res_hist_1[0]["to_state_id"] == st_nuevo

    # Movimiento legal Nuevo -> Contactado
    res_good_jump = api.client.post(f"/leads/{lead_id}/change_state", json={
        "new_state_id": st_contactado, "notes": "Lo llamé hoy"
    }, headers=api.headers)
    assert res_good_jump.status_code == 200
    assert res_good_jump.json()["current_state_id"] == st_contactado

    # Historial 2 verificado
    res_hist_2 = api.client.get(f"/lead_state_history/?lead_id={lead_id}", headers=api.headers).json()["items"]
    assert len(res_hist_2) == 2
    last_hist = max(res_hist_2, key=lambda x: x["id"])
    assert last_hist["from_state_id"] == st_nuevo
    assert last_hist["to_state_id"] == st_contactado

    # LEAD 2: UNHAPPY PATH — movimiento ilegal con lead separado para no contaminar el anterior
    res_lead_2 = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    lead_2_id = res_lead_2.json()["id"]

    res_bad_jump = api.client.post(f"/leads/{lead_2_id}/change_state", json={
        "new_state_id": st_ganado, "notes": "Cierre mágico"
    }, headers=api.headers)
    assert res_bad_jump.status_code == 400
    assert "Transición no permitida" in res_bad_jump.text


def test_lead_ghost_movement(api, flow_setup):
    """Movimiento Fantasma: Intentar mover un lead al mismo estado en el que ya está."""
    camp_valid = flow_setup["camp_valid_id"]
    st_nuevo   = flow_setup["state_nuevo_id"]

    res_lead = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    lead_id = res_lead.json()["id"]

    res_ghost = api.client.post(f"/leads/{lead_id}/change_state", json={
        "new_state_id": st_nuevo, "notes": "No me moví"
    }, headers=api.headers)

    assert res_ghost.status_code == 400
    assert "ya se encuentra en este estado" in res_ghost.text


# =============================================================================
# TESTS DE VALIDACIONES DE LEAD FLOW
# =============================================================================

def test_lead_flow_name_unique_per_org_create(api, flow_setup):
    """El nombre del flujo debe ser único dentro de la organización (create)."""
    res_create = api.client.post("/lead_flows/", json={"name": "Flujo de Ventas"}, headers=api.headers)
    assert res_create.status_code == 400
    assert "Ya existe un flujo" in res_create.text


def test_lead_flow_name_unique_per_org_update(api, flow_setup):
    """El nombre del flujo debe ser único dentro de la organización (update)."""
    empty_flow_id = flow_setup["flow_empty_id"]
    res_update = api.client.put(f"/lead_flows/{empty_flow_id}", json={"name": "Flujo de Ventas"}, headers=api.headers)
    assert res_update.status_code == 400
    assert "Ya existe un flujo" in res_update.text


# =============================================================================
# TESTS DE VALIDACIONES DE CAMPAÑAS Y FLUJOS
# =============================================================================

def test_campaign_prevent_flow_change_with_leads(api, flow_setup):
    """No se puede cambiar el lead_flow_id de una campaña si ya tiene leads."""
    camp_valid = flow_setup["camp_valid_id"]
    flow_empty = flow_setup["flow_empty_id"]

    api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)

    res = api.client.put(f"/campaigns/{camp_valid}", json={"lead_flow_id": flow_empty}, headers=api.headers)
    assert res.status_code == 400
    assert "ya tiene prospectos asignados" in res.text


def test_campaign_allow_flow_change_without_leads(api, flow_setup):
    """SÍ se puede cambiar el lead_flow_id de una campaña si NO tiene leads."""
    camp_empty = flow_setup["camp_empty_id"]
    flow_valid = flow_setup["flow_valid_id"]

    res = api.client.put(f"/campaigns/{camp_empty}", json={"lead_flow_id": flow_valid}, headers=api.headers)
    assert res.status_code == 200
    assert res.json()["lead_flow_id"] == flow_valid


# =============================================================================
# TESTS DE ELIMINACIÓN Y REORDENAMIENTO DE ESTADOS (LeadState)
# =============================================================================

def test_lead_state_prevent_delete_initial(api, flow_setup):
    """El sistema debe bloquear la eliminación de un estado inicial."""
    state_initial_id = flow_setup["state_nuevo_id"]

    res = api.client.delete(f"/lead_states/{state_initial_id}", headers=api.headers)
    assert res.status_code == 400
    assert "No se puede eliminar un estado inicial" in res.text


def test_lead_state_delete_reorders_open_states(api):
    """Al eliminar un estado OPEN, los estados siguientes deben reordenarse (restar 1 a su orden)."""
    f_res = api.client.post("/lead_flows/", json={"name": "Reorder Flow"}, headers=api.headers).json()
    f_id = f_res["id"]

    s1 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S1", "category": "OPEN", "is_initial": True}, headers=api.headers).json()
    s2 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S2", "category": "OPEN"}, headers=api.headers).json()
    s3 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S3", "category": "OPEN"}, headers=api.headers).json()

    assert s1["order"] == 1
    assert s2["order"] == 2
    assert s3["order"] == 3

    res_del = api.client.delete(f"/lead_states/{s2['id']}", headers=api.headers)
    assert res_del.status_code == 200

    s3_updated = api.client.get(f"/lead_states/{s3['id']}", headers=api.headers).json()
    assert s3_updated["order"] == 2


def test_lead_state_delete_with_active_leads_warns(api, flow_setup):
    """Con leads activos, el estado se desactiva (soft-delete) con un aviso en la respuesta."""
    camp_valid       = flow_setup["camp_valid_id"]
    st_contactado_id = flow_setup["state_contactado_id"]

    res_lead = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    lead_id = res_lead.json()["id"]
    api.client.post(f"/leads/{lead_id}/change_state", json={"new_state_id": st_contactado_id}, headers=api.headers)

    res_del = api.client.delete(f"/lead_states/{st_contactado_id}", headers=api.headers)

    # La operación debe completarse (no es un error)
    assert res_del.status_code == 200
    body = res_del.json()
    assert body.get("action") == "disabled"
    # Debe incluir un aviso informando sobre los leads activos
    assert "warning" in body
    assert "lead(s) activo" in body["warning"]

    # El estado queda inactivo: no debe aparecer en el listado activo del flujo
    estados_activos = api.client.get(
        f"/lead_states/?lead_flow_id={flow_setup['flow_valid_id']}&page_size=20",
        headers=api.headers
    ).json()["items"]
    ids_activos = [s["id"] for s in estados_activos]
    assert st_contactado_id not in ids_activos


def test_lead_state_delete_allowed_when_no_active_leads(api, flow_setup):
    """Sí se puede eliminar un estado OPEN si ningún lead está activo en él."""
    flow_id = flow_setup["flow_valid_id"]

    s_extra = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Extra sin leads", "category": "OPEN"
    }, headers=api.headers).json()

    res_del = api.client.delete(f"/lead_states/{s_extra['id']}", headers=api.headers)
    assert res_del.status_code == 200


# =============================================================================
# TESTS DE "CALLEJONES SIN SALIDA" — Transición individual
# =============================================================================

def test_transition_prevent_dead_end_on_delete(api, flow_setup):
    """Si al eliminar una transición un estado OPEN se queda con 0 salidas, debe fallar."""
    flow_id = flow_setup["flow_valid_id"]

    res_trans = api.client.get(f"/lead_state_transitions/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()
    t_nuevo_contactado = next(t for t in res_trans["items"] if t["from_state_id"] == flow_setup["state_nuevo_id"])

    res_del = api.client.delete(f"/lead_state_transitions/{t_nuevo_contactado['id']}", headers=api.headers)
    assert res_del.status_code == 400
    assert "quedaría sin ninguna ruta de salida" in res_del.text


# =============================================================================
# TESTS DE BULK — LeadStateTransition
# =============================================================================

def test_transition_bulk_create(api, bulk_flow_setup):
    """Prueba la creación masiva de transiciones (Bulk Create)."""
    f_id  = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    res_create = api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s2_id, "to_state_id": s3_id},
        ]
    }, headers=api.headers)

    assert res_create.status_code == 200
    assert len(res_create.json()) == 2


def test_transition_bulk_create_duplicate_within_request(api, bulk_flow_setup):
    """Bulk create rechaza si la misma transición aparece dos veces en el array del request."""
    f_id  = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]

    res = api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s1_id, "to_state_id": s2_id},
        ]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "duplicada" in res.text.lower()


def test_transition_bulk_create_nonexistent_state(api, bulk_flow_setup):
    """Bulk create falla con error claro cuando uno de los estados referenciados no existe."""
    f_id  = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]

    res = api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": 999999},
        ]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "no existe" in res.text


def test_transition_bulk_update_fails_on_dead_end(api, bulk_flow_setup):
    """Falla al hacer un update masivo si un estado OPEN queda sin salidas."""
    f_id  = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    res_update_fail = api.client.put("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s1_id, "to_state_id": s3_id},
        ]
    }, headers=api.headers)

    assert res_update_fail.status_code == 400
    assert "callejón sin salida" in res_update_fail.text


def test_transition_bulk_update_success(api, bulk_flow_setup):
    """
    Prueba la actualización masiva (sincronización) de transiciones con éxito,
    borrando lo viejo, manteniendo lo que sirve y creando lo nuevo.
    """
    f_id  = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s2_id, "to_state_id": s3_id},
        ]
    }, headers=api.headers)

    res_update_ok = api.client.put("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s1_id, "to_state_id": s3_id},
            {"from_state_id": s2_id, "to_state_id": s3_id},
        ]
    }, headers=api.headers)

    assert res_update_ok.status_code == 200
    assert len(res_update_ok.json()) == 3


# =============================================================================
# TESTS DEL ENDPOINT DE GRAFO — ORCHESTRATOR (/lead_flows/graph)
# =============================================================================

def test_graph_create_new_flow(api):
    """El Orchestrator crea un flujo completo desde cero usando IDs negativos."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Nuevo por Grafo",
        "description": "Creado via orchestrator",
        "states": [
            {"id": -1, "name": "Inicio",      "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": -2, "name": "Seguimiento", "category": "OPEN", "is_initial": False, "order": 2},
            {"id": -3, "name": "Cerrado",     "category": "WON",  "is_initial": False},
        ],
        "transitions": [
            {"from_state_id": -1, "to_state_id": -2},
            {"from_state_id": -2, "to_state_id": -3},
        ]
    }, headers=api.headers)

    assert res.status_code == 200
    assert "id" in res.json()

    flow_id = res.json()["id"]
    states      = api.client.get(f"/lead_states/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()["items"]
    transitions = api.client.get(f"/lead_state_transitions/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()["items"]

    assert len(states) == 3
    assert len(transitions) == 2
    assert sum(1 for s in states if s["is_initial"]) == 1


def test_graph_update_existing_flow(api, graph_flow_setup):
    """El Orchestrator actualiza un flujo: renombra, agrega un estado nuevo y rewire transiciones."""
    flow_id      = graph_flow_setup["flow_id"]
    s_inicio     = graph_flow_setup["s_inicio_id"]
    s_en_proceso = graph_flow_setup["s_en_proceso_id"]
    s_ganado     = graph_flow_setup["s_ganado_id"]

    res = api.client.post("/lead_flows/graph", json={
        "id": flow_id,
        "name": "Flujo Grafo Actualizado",
        "states": [
            {"id": s_inicio,     "name": "Inicio",     "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": s_en_proceso, "name": "En Proceso", "category": "OPEN", "is_initial": False, "order": 2},
            {"id": s_ganado,     "name": "Ganado",     "category": "WON",  "is_initial": False},
            {"id": -1,           "name": "Negociando", "category": "OPEN", "is_initial": False, "order": 3},
        ],
        "transitions": [
            {"from_state_id": s_inicio,     "to_state_id": s_en_proceso},
            {"from_state_id": s_en_proceso, "to_state_id": -1},
            {"from_state_id": -1,           "to_state_id": s_ganado},
        ]
    }, headers=api.headers)

    assert res.status_code == 200

    states = api.client.get(f"/lead_states/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()["items"]
    names = [s["name"] for s in states]
    assert "Negociando" in names
    assert len(states) == 4


def test_graph_fails_no_initial_state(api):
    """El Orchestrator rechaza un grafo sin ningun estado marcado como inicial."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Sin Inicial",
        "states": [
            {"id": -1, "name": "A", "category": "OPEN", "is_initial": False},
            {"id": -2, "name": "B", "category": "WON",  "is_initial": False},
        ],
        "transitions": [{"from_state_id": -1, "to_state_id": -2}]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "exactamente un (1) estado inicial" in res.text


def test_graph_fails_multiple_initial_states(api):
    """El Orchestrator rechaza un grafo con dos estados marcados como iniciales."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Doble Inicial",
        "states": [
            {"id": -1, "name": "A", "category": "OPEN", "is_initial": True},
            {"id": -2, "name": "B", "category": "OPEN", "is_initial": True},
        ],
        "transitions": [{"from_state_id": -1, "to_state_id": -2}]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "exactamente un (1) estado inicial" in res.text


def test_graph_fails_initial_state_not_open(api):
    """El Orchestrator rechaza cuando el estado inicial es WON o LOST."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Inicial WON",
        "states": [
            {"id": -1, "name": "Inicio Ganado", "category": "WON",  "is_initial": True},
            {"id": -2, "name": "Abierto",       "category": "OPEN", "is_initial": False},
        ],
        "transitions": [{"from_state_id": -2, "to_state_id": -1}]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "OPEN" in res.text


def test_graph_fails_dead_end_open_state(api):
    """El Orchestrator detecta callejones sin salida ANTES de mutar la base de datos."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Callejon",
        "states": [
            {"id": -1, "name": "Inicio",    "category": "OPEN", "is_initial": True},
            {"id": -2, "name": "Callejon",  "category": "OPEN", "is_initial": False},
            {"id": -3, "name": "Terminado", "category": "WON",  "is_initial": False},
        ],
        "transitions": [
            {"from_state_id": -1, "to_state_id": -2},
            {"from_state_id": -1, "to_state_id": -3},
        ]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "sin salida" in res.text


def test_graph_fails_remove_state_with_active_leads(api, graph_flow_setup):
    """El Orchestrator bloquea la eliminacion de un estado que tiene leads activos."""
    flow_id      = graph_flow_setup["flow_id"]
    s_inicio     = graph_flow_setup["s_inicio_id"]
    s_en_proceso = graph_flow_setup["s_en_proceso_id"]
    s_ganado     = graph_flow_setup["s_ganado_id"]
    camp_id      = graph_flow_setup["camp_id"]

    res_lead = api.client.post("/leads/", json={"campaign_id": camp_id, "values": []}, headers=api.headers)
    assert res_lead.status_code == 200, f"El lead no se creo: {res_lead.text}"

    res = api.client.post("/lead_flows/graph", json={
        "id": flow_id,
        "name": "Flujo Grafo Base",
        "states": [
            {"id": s_en_proceso, "name": "En Proceso", "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": s_ganado,     "name": "Ganado",     "category": "WON",  "is_initial": False},
        ],
        "transitions": [{"from_state_id": s_en_proceso, "to_state_id": s_ganado}]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "lead(s) activo" in res.text


def test_graph_respects_order_from_payload(api):
    """El campo order del payload se usa cuando viene explicito, sin importar el orden del array."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Con Orden Explicito",
        "states": [
            {"id": -1, "name": "Tercero",  "category": "OPEN", "is_initial": False, "order": 3},
            {"id": -2, "name": "Primero",  "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": -3, "name": "Segundo",  "category": "OPEN", "is_initial": False, "order": 2},
            {"id": -4, "name": "Terminal", "category": "WON",  "is_initial": False},
        ],
        "transitions": [
            {"from_state_id": -2, "to_state_id": -3},
            {"from_state_id": -3, "to_state_id": -1},
            {"from_state_id": -1, "to_state_id": -4},
        ]
    }, headers=api.headers)

    assert res.status_code == 200
    flow_id = res.json()["id"]

    states = api.client.get(f"/lead_states/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()["items"]
    order_map = {s["name"]: s["order"] for s in states if s["category"] == "OPEN"}

    assert order_map["Primero"] == 1
    assert order_map["Segundo"] == 2
    assert order_map["Tercero"] == 3


def test_graph_idempotent_on_repeated_save(api, graph_flow_setup):
    """Guardar el mismo grafo dos veces no duplica estados ni transiciones."""
    flow_id      = graph_flow_setup["flow_id"]
    s_inicio     = graph_flow_setup["s_inicio_id"]
    s_en_proceso = graph_flow_setup["s_en_proceso_id"]
    s_ganado     = graph_flow_setup["s_ganado_id"]

    payload = {
        "id": flow_id,
        "name": "Flujo Grafo Base",
        "states": [
            {"id": s_inicio,     "name": "Inicio",     "category": "OPEN", "is_initial": True,  "order": 1},
            {"id": s_en_proceso, "name": "En Proceso", "category": "OPEN", "is_initial": False, "order": 2},
            {"id": s_ganado,     "name": "Ganado",     "category": "WON",  "is_initial": False},
        ],
        "transitions": [
            {"from_state_id": s_inicio,     "to_state_id": s_en_proceso},
            {"from_state_id": s_en_proceso, "to_state_id": s_ganado},
        ]
    }

    res1 = api.client.post("/lead_flows/graph", json=payload, headers=api.headers)
    assert res1.status_code == 200

    res2 = api.client.post("/lead_flows/graph", json=payload, headers=api.headers)
    assert res2.status_code == 200

    states      = api.client.get(f"/lead_states/?lead_flow_id={flow_id}&page_size=50", headers=api.headers).json()["items"]
    transitions = api.client.get(f"/lead_state_transitions/?lead_flow_id={flow_id}&page_size=50", headers=api.headers).json()["items"]

    assert len(states) == 3
    assert len(transitions) == 2


def test_graph_name_conflict_rejected(api, flow_setup):
    """El Orchestrator rechaza un nombre ya usado por otro flujo en la misma organizacion."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo de Ventas",
        "states": [
            {"id": -1, "name": "A", "category": "OPEN", "is_initial": True},
            {"id": -2, "name": "B", "category": "WON",  "is_initial": False},
        ],
        "transitions": [{"from_state_id": -1, "to_state_id": -2}]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "Ya existe un flujo" in res.text


# =============================================================================
# TESTS DE ALLOWED NEXT STATES
# =============================================================================

def test_get_allowed_next_states(api, flow_setup):
    """next-states retorna exactamente los estados destino definidos por las transiciones."""
    s_nuevo      = flow_setup["state_nuevo_id"]
    s_contactado = flow_setup["state_contactado_id"]
    s_ganado     = flow_setup["state_ganado_id"]

    res = api.client.get(f"/lead_states/{s_nuevo}/next-states", headers=api.headers)
    assert res.status_code == 200

    ids = [s["id"] for s in res.json()["data"]]
    assert s_contactado in ids
    assert s_ganado not in ids
    assert s_nuevo not in ids


def test_get_allowed_next_states_terminal_state(api, flow_setup):
    """Un estado WON/LOST sin transiciones salientes retorna lista vacia."""
    s_ganado = flow_setup["state_ganado_id"]

    res = api.client.get(f"/lead_states/{s_ganado}/next-states", headers=api.headers)
    assert res.status_code == 200
    assert res.json()["data"] == []


# =============================================================================
# TESTS DE NUEVOS FIXES
# =============================================================================

def test_get_allowed_next_states_excludes_inactive(api, flow_setup):
    """Un estado soft-deleted no debe aparecer como proximo estado valido."""
    s_nuevo      = flow_setup["state_nuevo_id"]
    s_contactado = flow_setup["state_contactado_id"]

    api.client.delete(f"/lead_states/{s_contactado}", headers=api.headers)

    res = api.client.get(f"/lead_states/{s_nuevo}/next-states", headers=api.headers)
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["data"]]
    assert s_contactado not in ids


def test_lead_flow_name_reusable_after_delete(api):
    """El nombre de un flujo soft-deleted puede reutilizarse en un nuevo flujo."""
    res_create = api.client.post("/lead_flows/", json={"name": "Flujo Efimero"}, headers=api.headers)
    assert res_create.status_code == 200
    flow_id = res_create.json()["id"]

    api.client.delete(f"/lead_flows/{flow_id}", headers=api.headers)

    res_new = api.client.post("/lead_flows/", json={"name": "Flujo Efimero"}, headers=api.headers)
    assert res_new.status_code == 200
    assert res_new.json()["name"] == "Flujo Efimero"


def test_transition_prevent_self_loop(api, flow_setup):
    """No se puede crear una transicion de un estado hacia si mismo."""
    s_nuevo = flow_setup["state_nuevo_id"]
    flow_id = flow_setup["flow_valid_id"]

    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_id,
        "from_state_id": s_nuevo,
        "to_state_id": s_nuevo,
    }, headers=api.headers)

    assert res.status_code == 400
    assert "mismo" in res.text


def test_graph_category_validation(api):
    """El orchestrator rechaza categorias invalidas en StateNodeSchema (422 schema Pydantic)."""
    res = api.client.post("/lead_flows/graph", json={
        "name": "Flujo Categoria Invalida",
        "states": [
            {"id": -1, "name": "Inicio", "category": "INVALID", "is_initial": True},
            {"id": -2, "name": "Fin",    "category": "WON",     "is_initial": False},
        ],
        "transitions": [{"from_state_id": -1, "to_state_id": -2}]
    }, headers=api.headers)

    assert res.status_code == 422


def test_transition_schema_rejects_missing_from_state(api, flow_setup):
    """
    from_state_id es un campo requerido.
    Omitirlo por completo debe devolver 422 (error de schema Pydantic).
    """
    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_setup["flow_valid_id"],
        "to_state_id": flow_setup["state_nuevo_id"],
    }, headers=api.headers)

    assert res.status_code == 422
