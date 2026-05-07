import pytest
from datetime import datetime
from app.models.audit.lead_activity_history import LeadActivityHistory

# =============================================================================
# FIXTURE PARA EL ENTORNO DE AUTOMATIZACIONES
# =============================================================================

@pytest.fixture
def automations_setup(api):
    """
    Prepara un escenario limpio: Crea una Organización, un Flujo, una Campaña,
    3 Campos de prueba y un Lead vacío para poder hacer los Updates.
    """
    # 1. Crear Organización propia para aislar el test
    res_org = api.client.post("/organizations/", json={"name": "Org Automations Test"}, headers=api.headers).json()
    org_id = res_org["id"]
    
    old_org_id = api.org_id
    api.org_id = org_id

    # 2. Traer el flujo inyectado automáticamente (por tu infraestructura)
    flows = api.client.get("/lead_flows/", headers=api.headers).json()["items"]
    flow_id = flows[0]["id"]
    
    ws = api.client.post("/workspaces/", json={"name": "WS Automations", "organization_id": org_id}, headers=api.headers).json()
    camp = api.client.post("/campaigns/", json={"name": "Campaña Automations", "workspace_id": ws["id"], "lead_flow_id": flow_id}, headers=api.headers).json()
    camp_id = camp["id"]

    # 3. Crear 3 Campos para jugar con el motor
    f_condicion = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Condicion", "field_type_code": "STRING"}, headers=api.headers).json()
    f_resultado = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Resultado", "field_type_code": "STRING"}, headers=api.headers).json()
    f_fecha = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Fecha Auto", "field_type_code": "DATE"}, headers=api.headers).json()

    # 4. Crear un Lead base vacío
    lead = api.client.post("/leads/", json={"campaign_id": camp_id, "values": []}, headers=api.headers).json()

    yield {
        "org_id": org_id,
        "campaign_id": camp_id,
        "lead_id": lead["id"],
        "f_condicion_id": f_condicion["id"],
        "f_resultado_id": f_resultado["id"],
        "f_fecha_id": f_fecha["id"]
    }

    # Limpieza final
    api.org_id = old_org_id


# =============================================================================
# TESTS DEL MOTOR (FLUJO NORMAL Y AUDITORÍA)
# =============================================================================

def test_automation_normal_flow_on_update(api, automations_setup):
    """Debe aplicar el cambio de valor y setear la fecha al cumplirse la condición."""
    camp_id = automations_setup["campaign_id"]
    lead_id = automations_setup["lead_id"]
    f_cond = automations_setup["f_condicion_id"]
    f_res = automations_setup["f_resultado_id"]
    f_date = automations_setup["f_fecha_id"]

    # 1. Crear la Regla
    api.client.post("/field_automations/", json={
        "name": "Regla Normal",
        "campaign_id": camp_id,
        "trigger_events": ["ON_UPDATE"],
        "conditions": {
            "operator": "AND",
            "rules": [{"field_id": f_cond, "operator": "EQUALS", "value": ["Disparar"]}]
        },
        "actions": [
            {"type": "SET_VALUE", "target_field_id": f_res, "value": "Magia"},
            {"type": "SET_CURRENT_DATE", "target_field_id": f_date}
        ]
    }, headers=api.headers)

    # 2. Actualizar el Lead disparando la regla
    res_update = api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_cond, "value": "Disparar"}]
    }, headers=api.headers)

    assert res_update.status_code == 200
    
    # 3. Validar mutaciones en el payload de respuesta
    lead_data = res_update.json()
    vals = {fv["field_id"]: fv.get("value") for fv in lead_data.get("field_values", [])}
    
    assert vals.get(f_res) == "Magia"
    assert vals.get(f_date) == datetime.utcnow().strftime("%Y-%m-%d")


def test_automation_leaves_audit_trace(api, automations_setup, db_session):
    """Debe registrar en la DB que el cambio lo hizo la regla, asegurando la trazabilidad."""
    camp_id = automations_setup["campaign_id"]
    lead_id = automations_setup["lead_id"]
    f_cond = automations_setup["f_condicion_id"]
    f_res = automations_setup["f_resultado_id"]

    api.client.post("/field_automations/", json={
        "name": "Regla Auditoria",
        "campaign_id": camp_id,
        "trigger_events": ["ON_UPDATE"],
        "conditions": {
            "operator": "AND",
            "rules": [{"field_id": f_cond, "operator": "EQUALS", "value": ["Disparar"]}]
        },
        "actions": [{"type": "SET_VALUE", "target_field_id": f_res, "value": "Trazable"}]
    }, headers=api.headers)

    api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_cond, "value": "Disparar"}]
    }, headers=api.headers)

    # Consultar DB cruda para validar el historial
    historial = db_session.query(LeadActivityHistory).filter_by(
        lead_id=lead_id, activity_type="FIELDS_UPDATED"
    ).all()

    assert len(historial) > 0
    # Obtenemos los detalles del último cambio
    details = historial[-1].details.get("changes", {})
    
    # Validamos que inyectó el "source_rule"
    str_f_res = str(f_res)
    assert str_f_res in details
    assert details[str_f_res]["new_value"] == "Trazable"
    assert details[str_f_res]["source_rule"] == "Regla Auditoria"


# =============================================================================
# TESTS DE VULNERABILIDADES (DEFENSAS DEL MOTOR)
# =============================================================================

def test_vulnerability_infinite_loop_prevention(api, automations_setup):
    """El motor debe sobrevivir a un bucle cruzado sin agotar el timeout de la API."""
    camp_id = automations_setup["campaign_id"]
    lead_id = automations_setup["lead_id"]
    f_cond = automations_setup["f_condicion_id"]

    # Regla 1: 1 -> 2
    api.client.post("/field_automations/", json={
        "name": "Bucle 1", "campaign_id": camp_id, "trigger_events": ["ON_UPDATE"],
        "conditions": {"operator": "AND", "rules": [{"field_id": f_cond, "operator": "EQUALS", "value": ["1"]}]},
        "actions": [{"type": "SET_VALUE", "target_field_id": f_cond, "value": "2"}]
    }, headers=api.headers)

    # Regla 2: 2 -> 1
    api.client.post("/field_automations/", json={
        "name": "Bucle 2", "campaign_id": camp_id, "trigger_events": ["ON_UPDATE"],
        "conditions": {"operator": "AND", "rules": [{"field_id": f_cond, "operator": "EQUALS", "value": ["2"]}]},
        "actions": [{"type": "SET_VALUE", "target_field_id": f_cond, "value": "1"}]
    }, headers=api.headers)

    # Disparar la bomba. Si el cortafuegos MAX_CASCADES falla, esto dará un 504 Timeout o Crash.
    res_update = api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_cond, "value": "1"}]
    }, headers=api.headers)

    assert res_update.status_code == 200 # Sobrevivió!


def test_vulnerability_max_json_depth_prevention(api, automations_setup):
    """Debe prevenir Stack Overflow en Python al recibir un JSON abusivamente anidado."""
    camp_id = automations_setup["campaign_id"]
    lead_id = automations_setup["lead_id"]
    f_cond = automations_setup["f_condicion_id"]
    f_res = automations_setup["f_resultado_id"]

    # Armar árbol de 15 niveles de profundidad (superando nuestro max_depth=10)
    deep_tree = {"field_id": f_cond, "operator": "EQUALS", "value": ["Atacar"]}
    for _ in range(15):
        deep_tree = {"operator": "AND", "rules": [deep_tree]}

    # Creamos la regla destructiva
    api.client.post("/field_automations/", json={
        "name": "Bomba Depth", "campaign_id": camp_id, "trigger_events": ["ON_UPDATE"],
        "conditions": deep_tree,
        "actions": [{"type": "SET_VALUE", "target_field_id": f_res, "value": "Hackeado"}]
    }, headers=api.headers)

    # Ejecutar. Si el cortafuegos MAX_JSON_DEPTH falla, lanzará RecursionError (500).
    res_update = api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_cond, "value": "Atacar"}]
    }, headers=api.headers)

    assert res_update.status_code == 200
    
    # Comprobamos que el motor ABORTÓ la evaluación y NO aplicó la acción
    lead_data = res_update.json()
    vals = {fv["field_id"]: fv.get("value") for fv in lead_data.get("field_values", [])}
    assert vals.get(f_res) is None


def test_vulnerability_copy_from_empty_field(api, automations_setup):
    """Un COPY_FROM_FIELD desde un campo vacío/inexistente NO debe borrar el destino."""
    camp_id = automations_setup["campaign_id"]
    lead_id = automations_setup["lead_id"]
    f_cond = automations_setup["f_condicion_id"]
    f_res = automations_setup["f_resultado_id"]

    # 1. Le damos un valor valioso al campo resultado ("No Borrar")
    api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_res, "value": "Valor Valioso"}]
    }, headers=api.headers)

    # 2. Creamos la regla mal configurada (intenta copiar de un campo fantasma '999')
    api.client.post("/field_automations/", json={
        "name": "Copia Invalida", "campaign_id": camp_id, "trigger_events": ["ON_UPDATE"],
        "conditions": {"operator": "AND", "rules": [{"field_id": f_cond, "operator": "EQUALS", "value": ["Ejecutar"]}]},
        "actions": [{"type": "COPY_FROM_FIELD", "target_field_id": f_res, "source_field_id": 9999}]
    }, headers=api.headers)

    # 3. Disparamos la regla
    res_update = api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_cond, "value": "Ejecutar"}]
    }, headers=api.headers)

    assert res_update.status_code == 200
    
    # 4. Validamos que el "Valor Valioso" sobrevivió a la mala acción del motor
    lead_data = res_update.json()
    vals = {fv["field_id"]: fv.get("value") for fv in lead_data.get("field_values", [])}
    assert vals.get(f_res) == "Valor Valioso"