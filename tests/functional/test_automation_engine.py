import pytest
from datetime import datetime, timedelta
from app.models.audit.lead_activity_history import LeadActivityHistory
from app.models.lead import Lead
from app.models.lead_field import LeadField


def _internal_lead_id(db_session, lead_uuid):
    """Resuelve el public_uuid de un lead a su id interno -- LeadActivityHistory.lead_id
    es un FK int sin migrar (mismo patrón documentado en backend/AGENTS.md §18)."""
    return db_session.query(Lead.id).filter_by(public_uuid=lead_uuid).scalar()


def _internal_field_id(db_session, field_uuid):
    """Resuelve el public_uuid de un LeadField a su id interno -- el diccionario "changes"
    del audit log de FIELDS_UPDATED queda armado con el id interno crudo como key (nunca
    migrado a uuid), a diferencia de los ids de campo que devuelve la API."""
    return db_session.query(LeadField.id).filter_by(public_uuid=field_uuid).scalar()


# =============================================================================
# FIXTURE Y HELPERS
# =============================================================================

@pytest.fixture
def automations_setup(api):
    """
    Escenario aislado: Org propia, Campaña, 4 campos de prueba y un Lead vacío.
    Campos: Condicion (STRING), Resultado (STRING), Fecha Auto (DATE), Numero (INT)
    """
    res_org = api.client.post("/organizations/", json={"name": "Org Automations Test"}, headers=api.headers).json()
    org_id = res_org["id"]
    old_org_id = api.org_id
    api.org_id = org_id

    flows = api.client.get("/lead_flows/", headers=api.headers).json()["items"]
    flow_id = flows[0]["id"]

    ws = api.client.post("/workspaces/", json={"name": "WS Automations", "organization_id": org_id}, headers=api.headers).json()
    camp = api.client.post("/campaigns/", json={"name": "Campana Automations", "workspace_id": ws["id"], "lead_flow_id": flow_id}, headers=api.headers).json()
    camp_id = camp["id"]

    f_condicion = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Condicion", "field_type_code": "STRING"}, headers=api.headers).json()
    f_resultado = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Resultado", "field_type_code": "STRING"}, headers=api.headers).json()
    f_fecha     = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Fecha Auto", "field_type_code": "DATE"}, headers=api.headers).json()
    f_numero    = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Numero", "field_type_code": "INT"}, headers=api.headers).json()
    # Nomenclator con 3 ítems para el campo SELECTOR (APPEND/REMOVE necesitan IDs enteros)
    nom = api.client.post("/nomenclators/", json={"name": "Items Test"}, headers=api.headers).json()
    nom_id = nom["id"]
    item_a = api.client.post("/nomenclator_items/", json={"nomenclator_id": nom_id, "value": "Item A"}, headers=api.headers).json()
    item_b = api.client.post("/nomenclator_items/", json={"nomenclator_id": nom_id, "value": "Item B"}, headers=api.headers).json()
    item_c = api.client.post("/nomenclator_items/", json={"nomenclator_id": nom_id, "value": "Item C"}, headers=api.headers).json()
    f_lista = api.client.post("/lead_fields/", json={"campaign_id": camp_id, "name": "Lista", "field_type_code": "SELECTOR", "field_subtype_code": "SELECTOR_MULTIPLE", "nomenclator_id": nom_id}, headers=api.headers).json()

    lead = api.client.post("/leads/", json={"campaign_id": camp_id, "values": []}, headers=api.headers).json()

    yield {
        "org_id":        org_id,
        "campaign_id":   camp_id,
        "lead_id":       lead["id"],
        "f_condicion_id": f_condicion["id"],
        "f_resultado_id": f_resultado["id"],
        "f_fecha_id":    f_fecha["id"],
        "f_numero_id":   f_numero["id"],
        "f_lista_id":    f_lista["id"],
        "item_a_id":     item_a["id"],
        "item_b_id":     item_b["id"],
        "item_c_id":     item_c["id"],
    }

    api.org_id = old_org_id


def _vals(res):
    """Devuelve {field_id: value} del response de un lead.
    Para campos SELECTOR/LEAD (value=None), extrae los IDs de nomenclator_items.

    Bug real encontrado 2026-07-30: fv["field_id"] es el id interno crudo (int, sin migrar --
    ver LeadFieldValueResponse), pero los ids de campo que usa este archivo (s["f_condicion_id"],
    etc.) son public_uuid (Fase 4). Hay que indexar por el objeto anidado fv["field"]["id"], que
    sí es uuid.
    """
    result = {}
    for fv in res.json().get("field_values", []):
        field = fv.get("field") or {}
        fid = field.get("id")
        val = fv.get("value")
        if val is None:
            nom_items = fv.get("nomenclator_items", [])
            if nom_items:
                val = [item["id"] for item in nom_items]
        result[fid] = val
    return result


def _rule(api, camp_id, name, trigger, conditions, actions, priority=1):
    """Crea una FieldAutomation y devuelve el response."""
    return api.client.post("/field_automations/", json={
        "name": name,
        "campaign_id": camp_id,
        "trigger_events": [trigger],
        "conditions": conditions,
        "actions": actions,
        "priority": priority,
    }, headers=api.headers)


def _cond(field_id, operator, value=None):
    """Condición simple de un solo campo envuelta en un grupo AND."""
    node = {"field_id": field_id, "operator": operator}
    if value is not None:
        node["value"] = value
    return {"operator": "AND", "rules": [node]}


def _update(api, lead_id, camp_id, values, headers):
    """PUT /leads/{id} con una lista de {field_id, value}."""
    return api.client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id, "values": values
    }, headers=headers)


# =============================================================================
# FLUJO NORMAL Y AUDITORÍA
# =============================================================================

def test_automation_normal_flow_on_update(api, automations_setup):
    """SET_VALUE + SET_CURRENT_DATE deben aplicarse al cumplirse la condición en ON_UPDATE."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Normal", "ON_UPDATE",
        _cond(s["f_condicion_id"], "EQUALS", ["Disparar"]),
        [
            {"type": "SET_VALUE",        "target_field_id": s["f_resultado_id"], "value": "Magia"},
            {"type": "SET_CURRENT_DATE", "target_field_id": s["f_fecha_id"]},
        ]
    )

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Disparar"}], api.headers)

    assert res.status_code == 200
    vals = _vals(res)
    assert vals.get(s["f_resultado_id"]) == "Magia"
    assert vals.get(s["f_fecha_id"]) == datetime.utcnow().strftime("%Y-%m-%d")


def test_automation_on_create_trigger(api, automations_setup):
    """ON_CREATE debe disparar la regla al crear el lead, no solo en updates."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Creacion", "ON_CREATE",
        _cond(s["f_condicion_id"], "EQUALS", ["Nuevo"]),
        [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Creado"}]
    )

    res = api.client.post("/leads/", json={
        "campaign_id": s["campaign_id"],
        "values": [{"field_id": s["f_condicion_id"], "value": "Nuevo"}]
    }, headers=api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Creado"


def test_automation_leaves_audit_trace(api, automations_setup, db_session):
    """El audit_log debe registrar qué regla produjo el cambio."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Auditoria", "ON_UPDATE",
        _cond(s["f_condicion_id"], "EQUALS", ["Disparar"]),
        [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Trazable"}]
    )

    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_condicion_id"], "value": "Disparar"}], api.headers)

    historial = db_session.query(LeadActivityHistory).filter_by(
        lead_id=_internal_lead_id(db_session, s["lead_id"]), activity_type="FIELDS_UPDATED"
    ).all()
    assert len(historial) > 0
    details = historial[-1].details.get("changes", {})
    str_id = str(_internal_field_id(db_session, s["f_resultado_id"]))
    assert str_id in details
    assert details[str_id]["new_value"] == "Trazable"
    assert details[str_id]["source_rule"] == "Regla Auditoria"


def test_automation_condition_not_met_no_change(api, automations_setup):
    """Si la condición NO se cumple, el motor no debe tocar ningún campo."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Inerte", "ON_UPDATE",
        _cond(s["f_condicion_id"], "EQUALS", ["Disparar"]),
        [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "No deberia"}]
    )

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "OtraCosa"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) is None


# =============================================================================
# OPERADOR LÓGICO OR Y GRUPOS ANIDADOS
# =============================================================================

def test_automation_or_operator(api, automations_setup):
    """Con OR la regla debe disparar si AL MENOS UNA condición se cumple."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla OR", "ON_UPDATE",
        {
            "operator": "OR",
            "rules": [
                {"field_id": s["f_condicion_id"], "operator": "EQUALS", "value": ["Opcion A"]},
                {"field_id": s["f_condicion_id"], "operator": "EQUALS", "value": ["Opcion B"]},
            ]
        },
        [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "OR Cumplido"}]
    )

    # Solo se cumple la segunda rama del OR
    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Opcion B"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "OR Cumplido"


def test_automation_nested_groups(api, automations_setup):
    """Árbol anidado: (condicion == X AND fecha IS_NOT_EMPTY) OR resultado == Y"""
    s = automations_setup

    # Pre-cargamos fecha para que IS_NOT_EMPTY sea True
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_fecha_id"], "value": "2025-01-01"}], api.headers)

    _rule(api, s["campaign_id"], "Regla Anidada", "ON_UPDATE",
        {
            "operator": "OR",
            "rules": [
                {
                    "operator": "AND",
                    "rules": [
                        {"field_id": s["f_condicion_id"], "operator": "EQUALS", "value": ["Trigger"]},
                        {"field_id": s["f_fecha_id"],    "operator": "IS_NOT_EMPTY"},
                    ]
                },
                {"field_id": s["f_resultado_id"], "operator": "EQUALS", "value": ["Ya listo"]},
            ]
        },
        [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Anidado OK"}]
    )

    # Cumple el grupo AND interior
    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Trigger"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Anidado OK"


# =============================================================================
# ACCIONES BÁSICAS
# =============================================================================

def test_action_clear_value(api, automations_setup):
    """CLEAR_VALUE debe setear el campo destino a None."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_resultado_id"], "value": "Borrar esto"}], api.headers)

    _rule(api, s["campaign_id"], "Regla Clear", "ON_UPDATE",
        _cond(s["f_condicion_id"], "EQUALS", ["borrar"]),
        [{"type": "CLEAR_VALUE", "target_field_id": s["f_resultado_id"]}]
    )

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "borrar"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) is None


def test_action_copy_from_field_valid(api, automations_setup):
    """COPY_FROM_FIELD debe copiar el valor del campo origen cuando existe."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_condicion_id"], "value": "Valor original"}], api.headers)

    _rule(api, s["campaign_id"], "Regla Copy", "ON_UPDATE",
        _cond(s["f_condicion_id"], "IS_NOT_EMPTY"),
        [{"type": "COPY_FROM_FIELD", "target_field_id": s["f_resultado_id"],
          "source_field_id": s["f_condicion_id"]}]
    )

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Valor original"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Valor original"


def test_action_set_current_datetime(api, automations_setup):
    """SET_CURRENT_DATETIME debe guardar la fecha y hora en formato YYYY-MM-DD HH:MM:SS."""
    s = automations_setup
    f_dt = api.client.post("/lead_fields/", json={
        "campaign_id": s["campaign_id"], "name": "FechaHora", "field_type_code": "DATE_TIME"
    }, headers=api.headers).json()

    _rule(api, s["campaign_id"], "Regla Datetime", "ON_UPDATE",
        _cond(s["f_condicion_id"], "EQUALS", ["dt"]),
        [{"type": "SET_CURRENT_DATETIME", "target_field_id": f_dt["id"]}]
    )

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "dt"}], api.headers)

    assert res.status_code == 200
    val = _vals(res).get(f_dt["id"])
    assert val is not None
    datetime.strptime(val, "%Y-%m-%d %H:%M:%S")  # debe parsear sin error


# =============================================================================
# MÚLTIPLES AUTOMATIZACIONES Y PRIORIDAD
# =============================================================================

def test_multiple_automations_same_field_last_wins(api, automations_setup):
    """Dos reglas apuntan al mismo campo: la de mayor número de prioridad pisa a la anterior."""
    s = automations_setup
    cond = _cond(s["f_condicion_id"], "EQUALS", ["trigger"])

    _rule(api, s["campaign_id"], "Regla Primera", "ON_UPDATE", cond,
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Primera"}],
          priority=1)
    _rule(api, s["campaign_id"], "Regla Segunda", "ON_UPDATE", cond,
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Segunda"}],
          priority=2)

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "trigger"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Segunda"


def test_multiple_automations_same_field_audit_chain(api, automations_setup, db_session):
    """Cuando dos reglas tocan el mismo campo, source_rule debe encadenar ambos nombres."""
    s = automations_setup
    cond = _cond(s["f_condicion_id"], "EQUALS", ["trigger"])

    _rule(api, s["campaign_id"], "Regla A", "ON_UPDATE", cond,
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "A"}], priority=1)
    _rule(api, s["campaign_id"], "Regla B", "ON_UPDATE", cond,
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "B"}], priority=2)

    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_condicion_id"], "value": "trigger"}], api.headers)

    historial = db_session.query(LeadActivityHistory).filter_by(
        lead_id=_internal_lead_id(db_session, s["lead_id"]), activity_type="FIELDS_UPDATED"
    ).all()
    source_rule = historial[-1].details["changes"][str(_internal_field_id(db_session, s["f_resultado_id"]))]["source_rule"]
    assert "Regla A" in source_rule and "Regla B" in source_rule and "->" in source_rule


def test_cascade_effect(api, automations_setup):
    """Regla A cambia campo X → Regla B detecta ese cambio y actúa en la misma ejecución."""
    s = automations_setup

    # Regla A (priority=1): condicion == "inicio" → resultado = "intermedio"
    _rule(api, s["campaign_id"], "Cascada A", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["inicio"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "intermedio"}],
          priority=1)

    # Regla B (priority=2): resultado == "intermedio" → setear fecha
    _rule(api, s["campaign_id"], "Cascada B", "ON_UPDATE",
          _cond(s["f_resultado_id"], "EQUALS", ["intermedio"]),
          [{"type": "SET_CURRENT_DATE", "target_field_id": s["f_fecha_id"]}],
          priority=2)

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "inicio"}], api.headers)

    assert res.status_code == 200
    vals = _vals(res)
    assert vals.get(s["f_resultado_id"]) == "intermedio"
    assert vals.get(s["f_fecha_id"]) == datetime.utcnow().strftime("%Y-%m-%d")


def test_cascade_first_rule_blocks_second(api, automations_setup):
    """Regla A muta el campo que Regla B condicionaba, haciendo que B no se dispare."""
    s = automations_setup

    # Partimos con resultado = "original" ANTES de crear las reglas
    # (evita que Regla B se dispare durante el setup)
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_resultado_id"], "value": "original"}], api.headers)

    # Regla A (priority=1): condicion == "trigger" → resultado = "cambiado"
    _rule(api, s["campaign_id"], "Bloqueo A", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["trigger"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "cambiado"}],
          priority=1)

    # Regla B (priority=2): resultado == "original" → setear fecha (nunca debería disparar)
    _rule(api, s["campaign_id"], "Bloqueo B", "ON_UPDATE",
          _cond(s["f_resultado_id"], "EQUALS", ["original"]),
          [{"type": "SET_CURRENT_DATE", "target_field_id": s["f_fecha_id"]}],
          priority=2)

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "trigger"}], api.headers)

    assert res.status_code == 200
    vals = _vals(res)
    assert vals.get(s["f_resultado_id"]) == "cambiado"
    assert vals.get(s["f_fecha_id"]) is None  # B nunca matcheó


# =============================================================================
# OPERADORES DE CONDICIÓN
# =============================================================================

def test_condition_is_empty(api, automations_setup):
    """IS_EMPTY debe disparar cuando el campo no tiene valor."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Empty", "ON_UPDATE",
          _cond(s["f_resultado_id"], "IS_EMPTY"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Era vacio"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "cualquier"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Era vacio"


def test_condition_is_not_empty_does_not_fire_when_empty(api, automations_setup):
    """IS_NOT_EMPTY NO debe disparar cuando el campo está vacío."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Not Empty", "ON_UPDATE",
          _cond(s["f_resultado_id"], "IS_NOT_EMPTY"),
          [{"type": "SET_CURRENT_DATE", "target_field_id": s["f_fecha_id"]}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "algo"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_fecha_id"]) is None


def test_condition_greater_than_numeric(api, automations_setup):
    """GREATER_THAN debe comparar numéricamente: 10 > 9, no lexicográfico (evita '10' < '9')."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_numero_id"], "value": 10}], api.headers)

    _rule(api, s["campaign_id"], "Regla GT", "ON_UPDATE",
          _cond(s["f_numero_id"], "GREATER_THAN", 9),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Mayor"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_numero_id"], "value": 10}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Mayor"


def test_condition_less_than_date(api, automations_setup):
    """LESS_THAN con fechas YYYY-MM-DD debe comparar cronológicamente."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_fecha_id"], "value": "2020-01-01"}], api.headers)

    _rule(api, s["campaign_id"], "Regla LT Date", "ON_UPDATE",
          _cond(s["f_fecha_id"], "LESS_THAN", "2025-01-01"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Fecha anterior"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_fecha_id"], "value": "2020-01-01"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Fecha anterior"


def test_condition_contains(api, automations_setup):
    """CONTAINS debe disparar cuando el valor incluye el subconjunto dado."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Contains", "ON_UPDATE",
          _cond(s["f_condicion_id"], "CONTAINS", "ola"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Contiene"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "hola mundo"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Contiene"


def test_condition_not_contains(api, automations_setup):
    """NOT_CONTAINS NO debe disparar cuando el valor sí contiene el subconjunto."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla NotContains", "ON_UPDATE",
          _cond(s["f_condicion_id"], "NOT_CONTAINS", "spam"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Sin spam"}])

    # Caso positivo: no contiene "spam"
    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "correo limpio"}], api.headers)
    assert _vals(res).get(s["f_resultado_id"]) == "Sin spam"

    # Caso negativo: sí contiene "spam", NO debe disparar
    res2 = _update(api, s["lead_id"], s["campaign_id"],
                   [{"field_id": s["f_condicion_id"], "value": "es spam esto"}], api.headers)
    assert _vals(res2).get(s["f_resultado_id"]) == "Sin spam"  # valor no cambió


def test_condition_starts_with(api, automations_setup):
    """STARTS_WITH debe disparar solo cuando el valor empieza con el prefijo dado."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla StartsWith", "ON_UPDATE",
          _cond(s["f_condicion_id"], "STARTS_WITH", "admin"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Es admin"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "admin@empresa.com"}], api.headers)
    assert _vals(res).get(s["f_resultado_id"]) == "Es admin"

    # No empieza con "admin" → no debe cambiar
    res2 = _update(api, s["lead_id"], s["campaign_id"],
                   [{"field_id": s["f_condicion_id"], "value": "usuario@empresa.com"}], api.headers)
    assert _vals(res2).get(s["f_resultado_id"]) == "Es admin"


def test_condition_ends_with(api, automations_setup):
    """ENDS_WITH debe disparar solo cuando el valor termina con el sufijo dado."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla EndsWith", "ON_UPDATE",
          _cond(s["f_condicion_id"], "ENDS_WITH", ".com"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Es .com"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "correo@empresa.com"}], api.headers)
    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Es .com"


def test_condition_is_past(api, automations_setup):
    """IS_PAST debe disparar cuando el valor de fecha es anterior al momento actual."""
    s = automations_setup
    past = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_fecha_id"], "value": past}], api.headers)

    _rule(api, s["campaign_id"], "Regla IsPast", "ON_UPDATE",
          _cond(s["f_fecha_id"], "IS_PAST"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Vencida"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_fecha_id"], "value": past}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Vencida"


def test_condition_is_future(api, automations_setup):
    """IS_FUTURE NO debe disparar cuando la fecha ya pasó."""
    s = automations_setup
    past = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_fecha_id"], "value": past}], api.headers)

    _rule(api, s["campaign_id"], "Regla IsFuture", "ON_UPDATE",
          _cond(s["f_fecha_id"], "IS_FUTURE"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "No deberia"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_fecha_id"], "value": past}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) is None


def test_condition_dynamic_yesterday(api, automations_setup):
    """{{YESTERDAY}} debe resolverse a la fecha de ayer en tiempo de ejecución."""
    s = automations_setup
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_fecha_id"], "value": yesterday}], api.headers)

    _rule(api, s["campaign_id"], "Regla Yesterday", "ON_UPDATE",
          _cond(s["f_fecha_id"], "EQUALS", "{{YESTERDAY}}"),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Es ayer"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_fecha_id"], "value": yesterday}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Es ayer"


# =============================================================================
# NUEVAS ACCIONES
# =============================================================================

def test_action_increment_from_empty(api, automations_setup):
    """INCREMENT desde campo vacío debe partir de 0: resultado = 0 + 1 = 1."""
    s = automations_setup
    # Condición sobre el campo destino (IS_EMPTY): se auto-invalida al tener valor,
    # evitando que el cascade loop lo dispare más de una vez.
    _rule(api, s["campaign_id"], "Regla Inc", "ON_UPDATE",
          _cond(s["f_numero_id"], "IS_EMPTY"),
          [{"type": "INCREMENT", "target_field_id": s["f_numero_id"]}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "inc"}], api.headers)

    assert res.status_code == 200
    # INT fields se almacenan como string en DB; la API devuelve "1" no 1
    assert str(_vals(res).get(s["f_numero_id"])) == "1"


def test_action_increment_with_custom_step(api, automations_setup):
    """INCREMENT con step personalizado debe sumar exactamente ese valor."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_numero_id"], "value": 5}], api.headers)

    # Condición sobre el campo destino (EQUALS 5): se invalida cuando numero pasa a 15,
    # evitando que el cascade loop lo dispare más de una vez.
    _rule(api, s["campaign_id"], "Regla Inc Step", "ON_UPDATE",
          _cond(s["f_numero_id"], "EQUALS", [5]),
          [{"type": "INCREMENT", "target_field_id": s["f_numero_id"], "value": 10}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "inc"}], api.headers)

    assert res.status_code == 200
    # INT fields se almacenan como string en DB; la API devuelve "15" no 15
    assert str(_vals(res).get(s["f_numero_id"])) == "15"


def test_action_decrement(api, automations_setup):
    """DECREMENT debe restar el step del valor actual."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_numero_id"], "value": 10}], api.headers)

    # Condición sobre el campo destino (EQUALS 10): se invalida cuando numero pasa a 7,
    # evitando que el cascade loop lo dispare más de una vez.
    _rule(api, s["campaign_id"], "Regla Dec", "ON_UPDATE",
          _cond(s["f_numero_id"], "EQUALS", [10]),
          [{"type": "DECREMENT", "target_field_id": s["f_numero_id"], "value": 3}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "dec"}], api.headers)

    assert res.status_code == 200
    # INT fields se almacenan como string en DB; la API devuelve "7" no 7
    assert str(_vals(res).get(s["f_numero_id"])) == "7"


def test_action_set_date_offset_positive(api, automations_setup):
    """SET_DATE_OFFSET con N positivo debe resultar en hoy + N días."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Offset+", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["offset"]),
          [{"type": "SET_DATE_OFFSET", "target_field_id": s["f_fecha_id"], "value": 7}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "offset"}], api.headers)

    expected = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
    assert res.status_code == 200
    assert _vals(res).get(s["f_fecha_id"]) == expected


def test_action_set_date_offset_negative(api, automations_setup):
    """SET_DATE_OFFSET con N negativo debe resultar en hoy - N días."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Offset-", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["offset_neg"]),
          [{"type": "SET_DATE_OFFSET", "target_field_id": s["f_fecha_id"], "value": -30}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "offset_neg"}], api.headers)

    expected = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    assert res.status_code == 200
    assert _vals(res).get(s["f_fecha_id"]) == expected


def test_action_set_value_if_empty_fills_empty_field(api, automations_setup):
    """SET_VALUE_IF_EMPTY debe llenar el campo cuando está vacío."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla IfEmpty Fill", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["default"]),
          [{"type": "SET_VALUE_IF_EMPTY", "target_field_id": s["f_resultado_id"], "value": "Valor default"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "default"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Valor default"


def test_action_set_value_if_empty_respects_existing_value(api, automations_setup):
    """SET_VALUE_IF_EMPTY NO debe pisar un valor que ya existe."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_resultado_id"], "value": "Dato real"}], api.headers)

    _rule(api, s["campaign_id"], "Regla IfEmpty Respect", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["default"]),
          [{"type": "SET_VALUE_IF_EMPTY", "target_field_id": s["f_resultado_id"], "value": "Valor default"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "default"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Dato real"


def test_action_normalize_uppercase(api, automations_setup):
    """NORMALIZE_TEXT UPPERCASE debe convertir el texto a mayúsculas."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Upper", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["normalizar"]),
          [{"type": "NORMALIZE_TEXT", "target_field_id": s["f_resultado_id"], "value": "UPPERCASE"}])

    res = _update(api, s["lead_id"], s["campaign_id"], [
        {"field_id": s["f_condicion_id"], "value": "normalizar"},
        {"field_id": s["f_resultado_id"], "value": "hola mundo"},
    ], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "HOLA MUNDO"


def test_action_normalize_lowercase(api, automations_setup):
    """NORMALIZE_TEXT LOWERCASE debe convertir el texto a minúsculas."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Lower", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["normalizar"]),
          [{"type": "NORMALIZE_TEXT", "target_field_id": s["f_resultado_id"], "value": "LOWERCASE"}])

    res = _update(api, s["lead_id"], s["campaign_id"], [
        {"field_id": s["f_condicion_id"], "value": "normalizar"},
        {"field_id": s["f_resultado_id"], "value": "FRANCO RUIZ"},
    ], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "franco ruiz"


def test_action_normalize_trim(api, automations_setup):
    """NORMALIZE_TEXT TRIM debe eliminar espacios al inicio y al final."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Trim", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["normalizar"]),
          [{"type": "NORMALIZE_TEXT", "target_field_id": s["f_resultado_id"], "value": "TRIM"}])

    res = _update(api, s["lead_id"], s["campaign_id"], [
        {"field_id": s["f_condicion_id"], "value": "normalizar"},
        {"field_id": s["f_resultado_id"], "value": "  texto con espacios  "},
    ], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "texto con espacios"


def test_action_concat_fields(api, automations_setup):
    """CONCAT_FIELDS debe unir los valores de source_field_ids con el separador."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"], [
        {"field_id": s["f_condicion_id"], "value": "Franco"},
        {"field_id": s["f_resultado_id"], "value": "Ruiz"},
    ], api.headers)

    f_nombre = api.client.post("/lead_fields/", json={
        "campaign_id": s["campaign_id"], "name": "Nombre Completo", "field_type_code": "STRING"
    }, headers=api.headers).json()

    _rule(api, s["campaign_id"], "Regla Concat", "ON_UPDATE",
          _cond(s["f_condicion_id"], "IS_NOT_EMPTY"),
          [{
              "type": "CONCAT_FIELDS",
              "target_field_id": f_nombre["id"],
              "source_field_ids": [s["f_condicion_id"], s["f_resultado_id"]],
              "value": " "
          }])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Franco"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(f_nombre["id"]) == "Franco Ruiz"


def test_action_append_to_list_no_duplicates(api, automations_setup):
    """APPEND_TO_LIST no debe agregar duplicados si el ítem ya existe."""
    s = automations_setup
    # SELECTOR almacena IDs enteros de nomenclator items (no strings arbitrarias)
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_lista_id"], "value": [s["item_a_id"]]}], api.headers)

    _rule(api, s["campaign_id"], "Regla Append", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["append"]),
          [{"type": "APPEND_TO_LIST", "target_field_id": s["f_lista_id"],
            "value": [s["item_a_id"], s["item_b_id"]]}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "append"}], api.headers)

    assert res.status_code == 200
    val = _vals(res).get(s["f_lista_id"])
    assert isinstance(val, list)
    # item_a_id no duplicado, item_b_id agregado
    assert sorted(val) == sorted([s["item_a_id"], s["item_b_id"]])


def test_action_remove_from_list(api, automations_setup):
    """REMOVE_FROM_LIST debe quitar solo los ítems indicados."""
    s = automations_setup
    # SELECTOR almacena IDs enteros de nomenclator items (no strings arbitrarias)
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_lista_id"], "value": [s["item_a_id"], s["item_b_id"], s["item_c_id"]]}], api.headers)

    _rule(api, s["campaign_id"], "Regla Remove", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["remove"]),
          [{"type": "REMOVE_FROM_LIST", "target_field_id": s["f_lista_id"],
            "value": [s["item_b_id"]]}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "remove"}], api.headers)

    assert res.status_code == 200
    val = _vals(res).get(s["f_lista_id"])
    assert isinstance(val, list)
    # item_b_id removido, quedan item_a_id e item_c_id
    assert sorted(val) == sorted([s["item_a_id"], s["item_c_id"]])


def test_condition_on_selector_field_matches_via_public_uuid(api, automations_setup):
    """Regresión 2026-08-01 (ver backend/AGENTS.md §47): una condición sobre un campo
    SELECTOR nunca matcheaba porque RuleCondition.value llegaba como public_uuid de
    NomenclatorItem (lo único que expone la API/el front, ConditionRow.tsx) pero nunca se
    resolvía a id interno antes de compararlo contra LeadFieldValue (que sí guarda ids
    internos). item_a_id acá es el public_uuid real, igual que lo manda el front."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_lista_id"], "value": [s["item_a_id"]]}], api.headers)

    _rule(api, s["campaign_id"], "Regla Condicion Selector", "ON_UPDATE",
          _cond(s["f_lista_id"], "CONTAINS", [s["item_a_id"]]),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Selector Matcheo"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "trigger"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Selector Matcheo"


def test_action_set_value_on_selector_field_via_public_uuid(api, automations_setup):
    """Regresión 2026-08-01 (ver backend/AGENTS.md §47): SET_VALUE sobre un campo SELECTOR
    nunca resolvía el public_uuid de NomenclatorItem a id interno (solo estaba resuelto para
    APPEND_TO_LIST/REMOVE_FROM_LIST) -- guardaba el uuid crudo en LeadFieldValue.value,
    inconsistente con el resto del sistema. item_b_id acá es el public_uuid real."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Regla Set Value Selector", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["set_selector"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_lista_id"], "value": [s["item_b_id"]]}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "set_selector"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_lista_id"]) == [s["item_b_id"]]


def test_native_field_condition_and_action_resolve_public_uuid(api, automations_setup):
    """Regresión 2026-08-06 (reportado por el usuario, ver backend/AGENTS.md): mismo bug que
    los dos tests de arriba (campos SELECTOR), pero para campos NATIVOS (Etapa/Estado/Equipo/
    Asignado a). Una condición "Estado = X" nunca matcheaba porque RuleCondition.value llegaba
    como public_uuid de LeadContactState (lo que manda ConditionRow.tsx via getNativeIdOptions)
    pero nunca se resolvía a id interno antes de compararlo contra el contact_state_id real del
    lead -- la regla completa nunca se disparaba. Mismo problema del lado de la acción: SET_VALUE
    sobre Etapa (current_state_id) guardaba el public_uuid crudo de LeadState en vez de su id
    interno."""
    s = automations_setup

    contact_states = api.client.get("/lead_contact_states/", headers=api.headers).json()["items"]
    target_contact_state = next(cs for cs in contact_states if cs["name"] == "Rechazado")

    flows = api.client.get("/lead_flows/", headers=api.headers).json()["items"]
    flow_id = flows[0]["id"]
    lead_states = api.client.get("/lead_states/", params={"lead_flow_id": flow_id}, headers=api.headers).json()["items"]
    target_lead_state = next(ls for ls in lead_states if not ls["is_initial"])

    # -1 = Estado (contact_state_id), -2 = Etapa (current_state_id) -- ver
    # backend/app/core/native_lead_fields.py.
    _rule(api, s["campaign_id"], "Regla Estado -> Etapa", "ON_UPDATE",
          _cond(-1, "EQUALS", [target_contact_state["id"]]),
          [{"type": "SET_VALUE", "target_field_id": -2, "value": target_lead_state["id"]}])

    res = api.client.post(
        f"/leads/{s['lead_id']}/change_contact_state",
        json={"new_contact_state_id": target_contact_state["id"]},
        headers=api.headers,
    )

    assert res.status_code == 200
    body = res.json()
    assert body["contact_state"]["id"] == target_contact_state["id"]
    assert body["current_state"]["id"] == target_lead_state["id"]


# =============================================================================
# VULNERABILIDADES Y DEFENSAS
# =============================================================================

def test_vulnerability_infinite_loop_prevention(api, automations_setup):
    """El motor debe sobrevivir a un bucle cruzado sin colgar la API (MAX_CASCADES)."""
    s = automations_setup

    _rule(api, s["campaign_id"], "Bucle 1", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["1"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_condicion_id"], "value": "2"}])
    _rule(api, s["campaign_id"], "Bucle 2", "ON_UPDATE",
          _cond(s["f_condicion_id"], "EQUALS", ["2"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_condicion_id"], "value": "1"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "1"}], api.headers)

    assert res.status_code == 200


def test_vulnerability_max_json_depth_prevention(api, automations_setup):
    """El motor debe abortar y NO aplicar la acción ante un JSON abusivamente anidado."""
    s = automations_setup

    deep_tree = {"field_id": s["f_condicion_id"], "operator": "EQUALS", "value": ["Atacar"]}
    for _ in range(15):
        deep_tree = {"operator": "AND", "rules": [deep_tree]}

    api.client.post("/field_automations/", json={
        "name": "Bomba Depth", "campaign_id": s["campaign_id"],
        "trigger_events": ["ON_UPDATE"], "conditions": deep_tree,
        "actions": [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "Hackeado"}]
    }, headers=api.headers)

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Atacar"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) is None


def test_vulnerability_copy_from_empty_field(api, automations_setup):
    """COPY_FROM_FIELD desde campo inexistente NO debe borrar el destino."""
    s = automations_setup
    _update(api, s["lead_id"], s["campaign_id"],
            [{"field_id": s["f_resultado_id"], "value": "Valor Valioso"}], api.headers)

    api.client.post("/field_automations/", json={
        "name": "Copia Invalida", "campaign_id": s["campaign_id"],
        "trigger_events": ["ON_UPDATE"],
        "conditions": _cond(s["f_condicion_id"], "EQUALS", ["Ejecutar"]),
        "actions": [{"type": "COPY_FROM_FIELD", "target_field_id": s["f_resultado_id"],
                     "source_field_id": 9999}]
    }, headers=api.headers)

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "Ejecutar"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) == "Valor Valioso"


def test_deleted_rule_does_not_fire(api, automations_setup):
    """Una regla eliminada no debe ejecutarse. FieldAutomation no tiene hijos,
    por lo que DELETE siempre hace hard-delete (nunca soft-delete)."""
    s = automations_setup
    rule = _rule(api, s["campaign_id"], "Regla Eliminada", "ON_UPDATE",
                 _cond(s["f_condicion_id"], "EQUALS", ["disparar"]),
                 [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "No deberia"}]).json()

    del_res = api.client.delete(f"/field_automations/{rule['id']}", headers=api.headers)
    assert del_res.status_code == 200

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "disparar"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) is None


def test_wrong_event_rule_does_not_fire(api, automations_setup):
    """Una regla ON_CREATE no debe ejecutarse durante un ON_UPDATE."""
    s = automations_setup
    _rule(api, s["campaign_id"], "Solo Creacion", "ON_CREATE",
          _cond(s["f_condicion_id"], "EQUALS", ["disparar"]),
          [{"type": "SET_VALUE", "target_field_id": s["f_resultado_id"], "value": "No deberia"}])

    res = _update(api, s["lead_id"], s["campaign_id"],
                  [{"field_id": s["f_condicion_id"], "value": "disparar"}], api.headers)

    assert res.status_code == 200
    assert _vals(res).get(s["f_resultado_id"]) != "No deberia"