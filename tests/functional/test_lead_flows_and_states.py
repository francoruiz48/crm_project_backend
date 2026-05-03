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
    org_id = initial_structure["org_id"]
    ws_id = initial_structure["workspace_id"]
    
    # 1. Crear Flujos
    res_flow_1 = api.client.post("/lead_flows/", json={"name": "Flujo de Ventas"}, headers=api.headers)
    flow_1_id = res_flow_1.json()["id"]

    res_flow_2 = api.client.post("/lead_flows/", json={"name": "Flujo Vacío"}, headers=api.headers)
    flow_2_id = res_flow_2.json()["id"]

    # 2. Crear Estados en Flujo 1
    # Estado Inicial (Nuevo)
    s1 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_1_id, "name": "Nuevo", "category": "OPEN", "is_initial": True
    }, headers=api.headers).json()
    
    # Estado Intermedio (Contactado)
    s2 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_1_id, "name": "Contactado", "category": "OPEN", "is_initial": False
    }, headers=api.headers).json()

    # Estado Final (Ganado)
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
        "camp_empty_id": c2["id"]
    }


# =============================================================================
# TESTS DE LÓGICA DE ESTADOS (LeadStateService)
# =============================================================================

def test_lead_state_only_one_initial(api, flow_setup):
    """Guerra de estados iniciales: El sistema debe impedir 2 estados initial=True en un flujo."""
    flow_id = flow_setup["flow_valid_id"]

    # Intentar crear un segundo estado inicial
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

    # Caso 2: Nuevo estado LOST/WON enviando un order tramposo (Debe ignorar el 99 y poner null)
    res_lost = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Perdido", "category": "LOST", "is_initial": False, "order": 99
    }, headers=api.headers)
    assert res_lost.status_code == 200
    assert res_lost.json()["order"] is None

def test_lead_state_duplicate_order_prevented(api, flow_setup):
    """Evitar colisión de columnas visuales."""
    flow_id = flow_setup["flow_valid_id"]

    # Intento crear un estado con order=1 (que ya pertenece a 'Nuevo')
    res = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Pirata", "category": "OPEN", "order": 1
    }, headers=api.headers)
    
    assert res.status_code == 400
    assert "ya está en uso" in res.text


# =============================================================================
# TESTS DE GRAFO DE TRANSICIONES (LeadStateTransitionService)
# =============================================================================

def test_transition_prevent_cross_flow(api, flow_setup):
    """Evitar mezclar estados de Flujo A con estados de Flujo B."""
    f1_state_id = flow_setup["state_nuevo_id"]
    
    # Creo un estado en el Flujo 2
    s_f2 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_setup["flow_empty_id"], "name": "Inicio F2", "category": "OPEN"
    }, headers=api.headers).json()

    # Intento crear una flecha desde Flujo 1 hacia Flujo 2
    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_setup["flow_valid_id"], 
        "from_state_id": f1_state_id, 
        "to_state_id": s_f2["id"] # <--- Estado invasor
    }, headers=api.headers)

    assert res.status_code == 400
    assert "no pertenece al flujo" in res.text

def test_transition_prevent_duplicates(api, flow_setup):
    """No se puede registrar dos veces la misma flecha."""
    res = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_setup["flow_valid_id"], 
        "from_state_id": flow_setup["state_nuevo_id"], 
        "to_state_id": flow_setup["state_contactado_id"]
    }, headers=api.headers)

    assert res.status_code == 400
    assert "ya existe en el flujo" in res.text


# =============================================================================
# TESTS DEL CICLO DE VIDA DEL LEAD Y EL HISTORIAL
# =============================================================================

def test_create_lead_requires_initial_state(api, flow_setup):
    """Si la campaña usa un flujo vacío (sin estado inicial), no se puede crear el lead."""
    camp_empty = flow_setup["camp_empty_id"]

    res = api.client.post("/leads/", json={
        "campaign_id": camp_empty, "values": []
    }, headers=api.headers)

    assert res.status_code == 400
    assert "no tiene un flujo de estados válido" in res.text

def test_lead_lifecycle_and_history(api, flow_setup):
    """
    Simula la vida de un Lead:
    1. Creación (Nace en 'Nuevo' y guarda History 1).
    2. Movimiento Legal (Pasa a 'Contactado' -> Funciona y guarda History 2).
    3. Movimiento Ilegal (Intenta saltar a 'Ganado' desde otro lead -> Falla).
    """
    camp_valid = flow_setup["camp_valid_id"]
    st_nuevo = flow_setup["state_nuevo_id"]
    st_contactado = flow_setup["state_contactado_id"]
    st_ganado = flow_setup["state_ganado_id"]

    # ==========================================
    # LEAD 1: HAPPY PATH (Movimientos legales)
    # ==========================================
    res_lead = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    assert res_lead.status_code == 200
    lead_id = res_lead.json()["id"]
    assert res_lead.json()["current_state_id"] == st_nuevo

    # Validar Historial 1 (Big Bang)
    res_hist_1 = api.client.get(f"/lead_state_history/?lead_id={lead_id}", headers=api.headers).json()["items"]
    assert len(res_hist_1) == 1
    assert res_hist_1[0]["from_state_id"] is None
    assert res_hist_1[0]["to_state_id"] == st_nuevo

    # Movimiento Legal (Nuevo -> Contactado)
    res_good_jump = api.client.post(f"/leads/{lead_id}/change_state", json={
        "new_state_id": st_contactado, "notes": "Lo llamé hoy"
    }, headers=api.headers)
    assert res_good_jump.status_code == 200
    assert res_good_jump.json()["current_state_id"] == st_contactado

    # Validar Historial 2
    res_hist_2 = api.client.get(f"/lead_state_history/?lead_id={lead_id}", headers=api.headers).json()["items"]
    assert len(res_hist_2) == 2
    
    last_hist = max(res_hist_2, key=lambda x: x["id"])
    assert last_hist["from_state_id"] == st_nuevo
    assert last_hist["to_state_id"] == st_contactado

    # ==========================================
    # LEAD 2: UNHAPPY PATH (Movimientos ilegales)
    # ==========================================
    # Lo hacemos con un segundo lead para evitar que el Rollback 
    # de la base de datos arruine el test del Lead 1.
    res_lead_2 = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    lead_2_id = res_lead_2.json()["id"]

    # Movimiento Ilegal (Nuevo -> Ganado no existe en el fixture)
    res_bad_jump = api.client.post(f"/leads/{lead_2_id}/change_state", json={
        "new_state_id": st_ganado, "notes": "Cierre mágico"
    }, headers=api.headers)
    
    assert res_bad_jump.status_code == 400
    assert "Transición no permitida" in res_bad_jump.text


def test_lead_ghost_movement(api, flow_setup):
    """Movimiento Fantasma: Intentar mover un lead al mismo estado en el que ya está."""
    camp_valid = flow_setup["camp_valid_id"]
    st_nuevo = flow_setup["state_nuevo_id"]

    # Crear Lead (nace en 'Nuevo')
    res_lead = api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)
    lead_id = res_lead.json()["id"]

    # Intentar moverlo a 'Nuevo' de nuevo
    res_ghost = api.client.post(f"/leads/{lead_id}/change_state", json={
        "new_state_id": st_nuevo, "notes": "No me moví"
    }, headers=api.headers)
    
    assert res_ghost.status_code == 400
    assert "ya se encuentra en este estado" in res_ghost.text


# =============================================================================
# TESTS DE VALIDACIONES DE LEAD FLOW
# =============================================================================

def test_lead_flow_name_unique_per_org_create(api, flow_setup):
    """El nombre del flujo debe ser único dentro de la organización."""
    empty_flow_id = flow_setup["flow_empty_id"]

    # 1. Al crear: Intentar crear uno con el nombre del flujo válido ("Flujo de Ventas")
    res_create = api.client.post("/lead_flows/", json={
        "name": "Flujo de Ventas"
    }, headers=api.headers)
    assert res_create.status_code == 400
    assert "Ya existe un flujo" in res_create.text


def test_lead_flow_name_unique_per_org_update(api, flow_setup):
    """El nombre del flujo debe ser único dentro de la organización."""
    empty_flow_id = flow_setup["flow_empty_id"]

    # 2. Al actualizar: Intentar renombrar el flujo vacío al nombre del flujo válido
    res_update = api.client.put(f"/lead_flows/{empty_flow_id}", json={
        "name": "Flujo de Ventas"
    }, headers=api.headers)
    assert res_update.status_code == 400
    assert "Ya existe un flujo" in res_update.text


# =============================================================================
# TESTS DE VALIDACIONES DE CAMPAÑAS Y FLUJOS
# =============================================================================

def test_campaign_prevent_flow_change_with_leads(api, flow_setup):
    """No se puede cambiar el lead_flow_id de una campaña si ya tiene leads."""
    camp_valid = flow_setup["camp_valid_id"]
    flow_empty = flow_setup["flow_empty_id"]

    # Creamos un lead en la campaña válida
    api.client.post("/leads/", json={"campaign_id": camp_valid, "values": []}, headers=api.headers)

    # Intentamos cambiarle el flujo a la campaña
    res = api.client.put(f"/campaigns/{camp_valid}", json={
        "lead_flow_id": flow_empty
    }, headers=api.headers)

    assert res.status_code == 400
    assert "ya tiene prospectos asignados" in res.text

def test_campaign_allow_flow_change_without_leads(api, flow_setup):
    """SÍ se puede cambiar el lead_flow_id de una campaña si NO tiene leads."""
    camp_empty = flow_setup["camp_empty_id"]
    flow_valid = flow_setup["flow_valid_id"]

    # Cambiamos el flujo de la campaña vacía para que use el flujo válido
    res = api.client.put(f"/campaigns/{camp_empty}", json={
        "lead_flow_id": flow_valid
    }, headers=api.headers)

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
    # 1. Creamos un flujo temporal exclusivo para este test
    f_res = api.client.post("/lead_flows/", json={"name": "Reorder Flow"}, headers=api.headers).json()
    f_id = f_res["id"]

    # 2. Creamos 3 estados OPEN (El backend les asignará Order 1, 2 y 3)
    s1 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S1", "category": "OPEN", "is_initial": True}, headers=api.headers).json()
    s2 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S2", "category": "OPEN"}, headers=api.headers).json()
    s3 = api.client.post("/lead_states/", json={"lead_flow_id": f_id, "name": "S3", "category": "OPEN"}, headers=api.headers).json()

    assert s1["order"] == 1
    assert s2["order"] == 2
    assert s3["order"] == 3

    # 3. Eliminamos el del medio (S2)
    res_del = api.client.delete(f"/lead_states/{s2['id']}", headers=api.headers)
    assert res_del.status_code == 200

    # 4. Verificamos que S3 bajó al orden 2
    s3_updated = api.client.get(f"/lead_states/{s3['id']}", headers=api.headers).json()
    assert s3_updated["order"] == 2


# =============================================================================
# TESTS DE BULK Y "CALLEJONES SIN SALIDA" (LeadStateTransition)
# =============================================================================

def test_transition_prevent_dead_end_on_delete(api, flow_setup):
    """Si al eliminar una transición un estado OPEN se queda con 0 salidas, debe fallar."""
    flow_id = flow_setup["flow_valid_id"]
    
    # En el fixture creamos: Nuevo -> Contactado -> Ganado
    # Si borramos (Nuevo -> Contactado), "Nuevo" se queda en 0 salidas.
    
    # 1. Obtener las transiciones del flujo
    res_trans = api.client.get(f"/lead_state_transitions/?lead_flow_id={flow_id}&page_size=10", headers=api.headers).json()
    
    # Buscar la transición donde el origen es "Nuevo"
    t_nuevo_contactado = next(t for t in res_trans["items"] if t["from_state_id"] == flow_setup["state_nuevo_id"])

    # 2. Intentar eliminarla
    res_del = api.client.delete(f"/lead_state_transitions/{t_nuevo_contactado['id']}", headers=api.headers)
    
    assert res_del.status_code == 400
    assert "quedaría sin ninguna ruta de salida" in res_del.text


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
        "s3_id": s3["id"]
    }

def test_transition_bulk_create(api, bulk_flow_setup):
    """
    Prueba la creación masiva de transiciones (Bulk Create).
    """
    f_id = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    res_create = api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s2_id, "to_state_id": s3_id}
        ]
    }, headers=api.headers)
    
    assert res_create.status_code == 200
    assert len(res_create.json()) == 2


def test_transition_bulk_update_fails_on_dead_end(api, bulk_flow_setup):
    """
    Falla al hacer un update masivo si un estado OPEN queda sin salidas (Callejón sin salida).
    """
    f_id = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    # Intentamos mandar un nuevo grafo donde S1 va a S2, y S1 va a S3.
    # ¡Pero olvidamos ponerle una salida a S2! S2 se convertiría en un callejón sin salida.
    res_update_fail = api.client.put("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s1_id, "to_state_id": s3_id}
        ]
    }, headers=api.headers)
    
    assert res_update_fail.status_code == 400
    assert "callejón sin salida" in res_update_fail.text


def test_transition_bulk_update_success(api, bulk_flow_setup):
    """
    Prueba la actualización masiva (sincronización) de transiciones con éxito,
    borrando lo viejo, manteniendo lo que sirve y creando lo nuevo.
    """
    f_id = bulk_flow_setup["flow_id"]
    s1_id = bulk_flow_setup["s1_id"]
    s2_id = bulk_flow_setup["s2_id"]
    s3_id = bulk_flow_setup["s3_id"]

    # 1. Establecemos un estado inicial en la base de datos (S1 -> S2 -> S3)
    api.client.post("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id},
            {"from_state_id": s2_id, "to_state_id": s3_id}
        ]
    }, headers=api.headers)

    # 2. Corregimos el error del test anterior y agregamos una nueva ruta directa S1 -> S3. 
    # Mantenemos la salida de S2 para evitar el callejón sin salida.
    res_update_ok = api.client.put("/lead_state_transitions/bulk", json={
        "lead_flow_id": f_id,
        "transitions": [
            {"from_state_id": s1_id, "to_state_id": s2_id}, # Ya existía (se mantiene)
            {"from_state_id": s1_id, "to_state_id": s3_id}, # Nueva
            {"from_state_id": s2_id, "to_state_id": s3_id}  # Ya existía (se mantiene, evita el callejón)
        ]
    }, headers=api.headers)
    
    assert res_update_ok.status_code == 200
    assert len(res_update_ok.json()) == 3