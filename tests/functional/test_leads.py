import pytest
from app.models.lead_field import LeadField
from app.models.lead_field_section import LeadFieldSection
from app.models.lead_state import LeadState
from app.models.lead_flow import LeadFlow
from app.models.workspace import Workspace
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.campaign import Campaign
from app.models.team import Team
from app.models.security_models import User, UserOrganization
from app.models.lead_contact_state import LeadContactState


def _resolve_internal_id(db_session, model, public_uuid_or_int):
    """
    initial_structure devuelve public_uuid para campaign_id/section_id/workspace_id/
    lead_flow_id (Fase 3), pero este archivo construye filas ORM (LeadField/Campaign/
    LeadState) directo en la DB, que necesitan el id interno (columnas FK Integer reales).
    """
    if isinstance(public_uuid_or_int, int):
        return public_uuid_or_int
    return db_session.query(model.id).filter_by(public_uuid=public_uuid_or_int).scalar()

# --- TESTS BÁSICOS ---

def test_get_empty_leads(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    response = api.client.get(f"/leads?campaign_id={camp_id}", headers=api.headers)
    assert response.status_code == 200
    
    data = response.json()
    if isinstance(data, dict) and "items" in data:
        assert data["items"] == []
        assert data["total"] == 0
    else:
        assert data == []

def test_create_lead_simple_values(api, initial_fields):
    camp_id = initial_fields["campaign_id"]
    
    # Ya no hacemos initial_fields["nombre"].id
    field_nombre_id = initial_fields["nombre_id"]
    field_edad_id = initial_fields["edad_id"]

    values = [
        {"field_id": field_nombre_id, "value": "Carlos Test"},
        {"field_id": field_edad_id, "value": "45"}
    ]

    data = api.create_lead(campaign_id=camp_id, values=values, expected_status=200)
    assert data["id"] is not None
    
    val_nombre = next((v for v in data["field_values"] if v["field"]["id"] == field_nombre_id), None)
    assert val_nombre["value"] == "Carlos Test"

def test_create_lead_missing_required(api, initial_fields):
    camp_id = initial_fields["campaign_id"]
    # Solo enviamos edad (opcional), falta nombre (obligatorio)
    values = [{"field_id": initial_fields["edad_id"], "value": 30}]

    res_fail = api.create_lead(campaign_id=camp_id, values=values, expected_status=False)
    assert res_fail.status_code == 400
    assert "obligatorio" in res_fail.text.lower()


def test_create_lead_various_types(api, db_session, initial_structure):
    """
    Prueba la creación de campos con tipos variados (DATE, BOOL, NUMBER) 
    y verifica que se guarden correctamente.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_fecha = LeadField(name="Fecha Nacimiento", field_type_code="DATE", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    f_vip = LeadField(name="Es VIP", field_type_code="BOOL", campaign_id=camp_internal_id, order=2, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    f_score = LeadField(name="Puntaje", field_type_code="NUMBER", campaign_id=camp_internal_id, order=3, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    
    db_session.add_all([f_fecha, f_vip, f_score])
    db_session.commit()

    values = [
        {"field_id": f_fecha.id, "value": "1990-12-31"},
        {"field_id": f_vip.id, "value": "true"}, 
        {"field_id": f_score.id, "value": "98.5"}
    ]

    data = api.create_lead(campaign_id=camp_id, values=values, expected_status=200)
    
    vals = {v["field_id"]: v["value"] for v in data["field_values"]}
    assert vals[f_fecha.id] == "1990-12-31"
    assert str(vals[f_vip.id]).lower() == "true" 
    assert str(vals[f_score.id]) == "98.5"


def test_create_lead_input_mask_validation_failure(api, db_session, initial_structure):
    """
    Caso Fallido: La máscara AAA-### debe rechazar formatos incorrectos.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_patente = LeadField(name="Patente Fail", field_type_code="STRING", campaign_id=camp_internal_id, input_mask="AAA-###", order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_patente)
    db_session.commit()

    values = [{"field_id": f_patente.id, "value": "ABC-12"}]
    res_fail = api.create_lead(campaign_id=camp_id, values=values, expected_status=False)
    assert res_fail.status_code == 400


def test_create_lead_input_mask_validation_success(api, db_session, initial_structure):
    """
    Caso Exitoso: La máscara AAA-### debe aceptar formatos correctos.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_patente = LeadField(name="Patente OK", field_type_code="STRING", campaign_id=camp_internal_id, input_mask="AAA-###", order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_patente)
    db_session.commit()

    values = [{"field_id": f_patente.id, "value": "ABC-123"}]
    data = api.create_lead(campaign_id=camp_id, values=values, expected_status=200)

    val_guardado = next(v for v in data["field_values"] if v["field_id"] == f_patente.id)
    assert val_guardado["value"] == "ABC-123"
    

def test_create_lead_duplicate_primary_field(api, db_session, initial_structure):
    """
    Prueba que no se puedan crear dos leads con el mismo valor en un campo 'is_primary' (Unique).
    Ejemplo: DNI o Email.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    # 1. Campo Primary (DNI)
    f_dni = LeadField(name="DNI", field_type_code="STRING", campaign_id=camp_internal_id, is_primary=True, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_dni)
    db_session.commit()

    # 2. Crear Primer Lead
    values = [{"field_id": f_dni.id, "value": "12345678"}]
    api.create_lead(campaign_id=camp_id, values=values, expected_status=200)

    # 3. Intentar crear Segundo Lead con MISMO DNI
    res_dup = api.create_lead(campaign_id=camp_id, values=values, expected_status=False)
    assert res_dup.status_code in [409, 400] #Debe fallar


def test_lead_lifecycle(api, initial_fields):
    """
    Prueba el flujo completo: Crear -> Editar -> Desactivar -> Reactivar -> Borrar.
    """
    camp_id = initial_fields["campaign_id"]
    f_nombre = initial_fields["nombre_id"]
    
    # CREAR
    data = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre, "value": "Juan Original"}], expected_status=200)
    lead_id = data["id"]
    
    # EDITAR (PUT)
    data_updated = api.update_lead(lead_id=lead_id, campaign_id=camp_id, values=[{"field_id": f_nombre, "value": "Juan Editado"}], expected_status=200)
    val_editado = next(v for v in data_updated["field_values"] if v["field"]["id"] == f_nombre)
    assert val_editado["value"] == "Juan Editado"
    
    # BORRAR
    api.delete_lead(lead_id=lead_id, expected_status=200)
    
    # VERIFICAR BORRADO
    api.get_lead(lead_id=lead_id, expected_status=404)   

def test_search_leads_advanced(api, db_session, initial_structure):
    """
    Prueba el endpoint de búsqueda con filtros complejos (Rangos y Texto).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    # 1. Setup Campos (Edad y Nombre)
    f_edad = LeadField(name="Edad", field_type_code="INT", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    f_nombre = LeadField(name="Nombre", field_type_code="STRING", campaign_id=camp_internal_id, order=2, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add_all([f_edad, f_nombre])
    db_session.commit()

    # 2. Crear Datos de Prueba (Usamos el helper api)
    # Lead 1: Ana, 25
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_nombre.id, "value": "Ana"}, {"field_id": f_edad.id, "value": "25"}]
    )
    # Lead 2: Beto, 40
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_nombre.id, "value": "Beto"}, {"field_id": f_edad.id, "value": "40"}]
    )
    # Lead 3: Carlos, 60
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_nombre.id, "value": "Carlos"}, {"field_id": f_edad.id, "value": "60"}]
    )

    # 3. Test: Mayor o igual a 40 (gte)
    payload_gte = {
        "page": 1, 
        "page_size": 10,
        "filters": [
            {"field_id": f_edad.id, "operator": "gte", "value": "40"}
        ]
    }
    # Para search, como no está en api_helpers todavía, usamos api.client inyectando headers
    res_gte = api.client.post("/leads/search", json=payload_gte, headers=api.headers)
    assert res_gte.status_code == 200
    data_gte = res_gte.json()["items"]
    assert len(data_gte) == 2 # Beto y Carlos

    # 4. Test: Texto que contiene 'rl' (like) -> Carlos
    payload_like = {
        "page": 1,
        "filters": [
            {"field_id": f_nombre.id, "operator": "ilike", "value": "rl"} # ilike ignora mayúsculas
        ]
    }
    res_like = api.client.post("/leads/search", json=payload_like, headers=api.headers)
    assert res_like.status_code == 200
    data_like = res_like.json()["items"]
    assert len(data_like) == 1
    
    # Validamos que sea Carlos
    vals = data_like[0]["field_values"]
    nombre_val = next(v for v in vals if v["field_id"] == f_nombre.id)
    assert nombre_val["value"] == "Carlos"

    # 5. Test: Rango de Edad (between) 20 y 30 -> Ana
    payload_between = {
        "page": 1,
        "filters": [
            {"field_id": f_edad.id, "operator": "between", "value": ["20", "30"]} 
        ]
    }
    res_between = api.client.post("/leads/search", json=payload_between, headers=api.headers)
    assert res_between.status_code == 200
    data_between = res_between.json()["items"]
    assert len(data_between) == 1 # Solo Ana


def test_search_leads_range_two_filters_same_field(api, db_session, initial_structure):
    """
    Bug real encontrado 2026-08-11 (reportado por el usuario -- filtro de rango de un campo
    NUMBER "no estaría filtrando bien"): a diferencia de test_search_leads_advanced (que prueba
    el operador "between", un único LeadFilter con value=[min, max]), el front real NUNCA manda
    "between" -- LeadFilters.tsx::onSubmit arma un rango Desde/Hasta como DOS LeadFilter
    separados sobre el mismo field_id (uno "gte", uno "lte"). LeadRepository.search() agrupaba
    todas las condiciones de un mismo field_id con OR, así que ese par terminaba siendo
    "valor >= Desde OR valor <= Hasta" -- matchea casi cualquier valor, no filtra el rango.
    Cubre el caso real (NUMBER e INT) con dos filtros separados, y que el resto de la
    combinación (OR entre condiciones no-rango) sigue intacto.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_edad = LeadField(name="Edad Rango", field_type_code="INT", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    f_puntaje = LeadField(name="Puntaje Rango", field_type_code="NUMBER", campaign_id=camp_internal_id, order=2, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add_all([f_edad, f_puntaje])
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_edad.id, "value": "25"}, {"field_id": f_puntaje.id, "value": "10.5"}])   # Ana
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_edad.id, "value": "40"}, {"field_id": f_puntaje.id, "value": "50.0"}])   # Beto
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_edad.id, "value": "60"}, {"field_id": f_puntaje.id, "value": "90.0"}])   # Carlos

    # Rango [30, 50] sobre INT (Edad) armado como dos filtros separados, igual que manda el
    # front real -> debe traer solo a Beto (40), no a los tres.
    payload_range = {
        "page": 1,
        "filters": [
            {"field_id": f_edad.id, "operator": "gte", "value": 30},
            {"field_id": f_edad.id, "operator": "lte", "value": 50},
        ]
    }
    res_range = api.client.post("/leads/search", json=payload_range, headers=api.headers)
    assert res_range.status_code == 200
    data_range = res_range.json()["items"]
    assert len(data_range) == 1
    vals = {v["field_id"]: v["value"] for v in data_range[0]["field_values"]}
    assert vals[f_edad.id] == "40"

    # Mismo caso sobre NUMBER (Puntaje), rango [20.0, 60.0] -> debe traer solo a Beto (50.0).
    payload_range_number = {
        "page": 1,
        "filters": [
            {"field_id": f_puntaje.id, "operator": "gte", "value": 20.0},
            {"field_id": f_puntaje.id, "operator": "lte", "value": 60.0},
        ]
    }
    res_range_number = api.client.post("/leads/search", json=payload_range_number, headers=api.headers)
    assert res_range_number.status_code == 200
    data_range_number = res_range_number.json()["items"]
    assert len(data_range_number) == 1
    vals_number = {v["field_id"]: v["value"] for v in data_range_number[0]["field_values"]}
    assert vals_number[f_puntaje.id] == "50.0"

    # Rango que no matchea a nadie (Edad entre 100 y 200) -> debe devolver vacío, no todos.
    payload_range_empty = {
        "page": 1,
        "filters": [
            {"field_id": f_edad.id, "operator": "gte", "value": 100},
            {"field_id": f_edad.id, "operator": "lte", "value": 200},
        ]
    }
    res_range_empty = api.client.post("/leads/search", json=payload_range_empty, headers=api.headers)
    assert res_range_empty.status_code == 200
    assert res_range_empty.json()["items"] == []


def test_search_leads_date_range_two_filters_same_field(api, db_session, initial_structure):
    """
    Mismo caso que test_search_leads_range_two_filters_same_field pero para DATE, que comparte
    exactamente el mismo código de agrupado (gte/lte del mismo field_id -> AND). Cubre además el
    caso de un solo lado del rango (solo "Desde", sin "Hasta") -- LeadFilters.tsx::onSubmit no
    siempre manda los dos operadores.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_fecha = LeadField(name="Fecha Alta", field_type_code="DATE", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_fecha)
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_fecha.id, "value": "2020-01-01"}])   # fuera de rango
    lead_mid = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_fecha.id, "value": "2022-06-15"}])   # dentro
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_fecha.id, "value": "2024-12-31"}])   # fuera de rango (por arriba)

    # Rango [2021-01-01, 2023-01-01] -> solo el lead de en medio.
    res = api.client.post("/leads/search", json={
        "page": 1,
        "filters": [
            {"field_id": f_fecha.id, "operator": "gte", "value": "2021-01-01"},
            {"field_id": f_fecha.id, "operator": "lte", "value": "2023-01-01"},
        ]
    }, headers=api.headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == lead_mid["id"]

    # Un solo lado del rango (solo "Desde") -> los dos leads más nuevos.
    res_single = api.client.post("/leads/search", json={
        "page": 1,
        "filters": [{"field_id": f_fecha.id, "operator": "gte", "value": "2022-01-01"}]
    }, headers=api.headers)
    assert res_single.status_code == 200
    assert len(res_single.json()["items"]) == 2


def test_search_leads_bool_filter(api, db_session, initial_structure):
    """
    Cobertura de un campo BOOL filtrado con el payload exacto que arma LeadFilters.tsx::onSubmit
    ("Es verdadero"/"Es falso" -> operator eq, value 1/0 -- entero, no string). El valor se crea
    con un booleano JSON crudo (True/False), igual que manda el switch real del formulario de
    Lead (ControlledSwitch) -- no la forma en que test_create_lead_various_types lo arma más
    arriba (string "true" a mano, atajo válido pero no representativo del payload real).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_vip = LeadField(name="Es VIP", field_type_code="BOOL", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_vip)
    db_session.commit()

    lead_vip = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_vip.id, "value": True}])
    lead_no_vip = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_vip.id, "value": False}])

    res_true = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": f_vip.id, "operator": "eq", "value": 1}]
    }, headers=api.headers)
    assert res_true.status_code == 200
    items_true = res_true.json()["items"]
    assert len(items_true) == 1
    assert items_true[0]["id"] == lead_vip["id"]

    res_false = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": f_vip.id, "operator": "eq", "value": 0}]
    }, headers=api.headers)
    assert res_false.status_code == 200
    items_false = res_false.json()["items"]
    assert len(items_false) == 1
    assert items_false[0]["id"] == lead_no_vip["id"]


def test_search_leads_selector_in_multiselect(api, db_session, initial_structure):
    """
    Cobertura de un campo SELECTOR filtrado con operator="in" y varios public_uuid de
    NomenclatorItem en value (formato real que arma LeadFilters.tsx tras el fix del
    2026-08-11 que sacó el Number() de apiFiltersToFormFilters/value_ids -- ver
    _resolve_item_id en lead_repository.py, que ya resolvía uuid->interno correctamente del
    lado del backend, pero no tenía cobertura para el caso multi-select).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    nomenclator = Nomenclator(name="Colores", organization_id=org_id)
    db_session.add(nomenclator)
    db_session.flush()
    item_rojo = NomenclatorItem(nomenclator_id=nomenclator.id, value="Rojo", organization_id=org_id)
    item_azul = NomenclatorItem(nomenclator_id=nomenclator.id, value="Azul", organization_id=org_id)
    item_verde = NomenclatorItem(nomenclator_id=nomenclator.id, value="Verde", organization_id=org_id)
    db_session.add_all([item_rojo, item_azul, item_verde])
    db_session.commit()

    f_color = LeadField(name="Color", field_type_code="SELECTOR", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True, nomenclator_id=nomenclator.id)
    db_session.add(f_color)
    db_session.commit()

    lead_rojo = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_color.id, "value": item_rojo.id}])
    lead_azul = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_color.id, "value": item_azul.id}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_color.id, "value": item_verde.id}])   # no debe aparecer

    res = api.client.post("/leads/search", json={
        "page": 1,
        "filters": [{"field_id": f_color.id, "operator": "in", "value": [item_rojo.public_uuid, item_azul.public_uuid]}]
    }, headers=api.headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert {i["id"] for i in items} == {lead_rojo["id"], lead_azul["id"]}


def test_search_leads_native_id_in_multiselect(api, db_session, initial_structure):
    """
    Cobertura de team_id (NATIVE_ID) filtrado con operator="in" y varios public_uuid de Team --
    mismo formato que manda LeadFilters.tsx para un NATIVE_ID multi-select. Los tests de
    test_search_leads_native_fields de arriba solo cubren "eq" (una sola selección).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre Native In", field_type_code="STRING", required=False)

    team_a = Team(name="Equipo A", organization_id=org_id)
    team_b = Team(name="Equipo B", organization_id=org_id)
    team_c = Team(name="Equipo C", organization_id=org_id)
    db_session.add_all([team_a, team_b, team_c])
    db_session.commit()

    lead_a = api.create_lead(campaign_id=camp_id, values=[])
    lead_b = api.create_lead(campaign_id=camp_id, values=[])
    lead_c = api.create_lead(campaign_id=camp_id, values=[])
    api.bulk_assign(lead_ids=[lead_a["id"]], target_team_id=team_a.public_uuid)
    api.bulk_assign(lead_ids=[lead_b["id"]], target_team_id=team_b.public_uuid)
    api.bulk_assign(lead_ids=[lead_c["id"]], target_team_id=team_c.public_uuid)   # no debe aparecer

    res = api.client.post("/leads/search", json={
        "page": 1,
        "filters": [{"field_id": "team_id", "operator": "in", "value": [team_a.public_uuid, team_b.public_uuid]}]
    }, headers=api.headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert {i["id"] for i in items} == {lead_a["id"], lead_b["id"]}


def test_search_leads_string_or_same_field_regression(api, db_session, initial_structure):
    """
    Regresión: dos filtros STRING (ilike) sobre el MISMO campo deben seguir combinándose con OR
    ("contiene 'Ana'" OR "contiene 'Beto'") -- el fix de rango del 2026-08-11 (AND para
    gt/lt/gte/lte del mismo campo) no debe afectar este caso, que sigue usando OR.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_nombre = LeadField(name="Nombre OR", field_type_code="STRING", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_nombre)
    db_session.commit()

    lead_ana = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Ana"}])
    lead_beto = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Beto"}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Carlos"}])   # no debe aparecer

    res = api.client.post("/leads/search", json={
        "page": 1,
        "filters": [
            {"field_id": f_nombre.id, "operator": "ilike", "value": "Ana"},
            {"field_id": f_nombre.id, "operator": "ilike", "value": "Beto"},
        ]
    }, headers=api.headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert {i["id"] for i in items} == {lead_ana["id"], lead_beto["id"]}


def test_search_leads_text_query(api, db_session, initial_structure):
    """
    Regresión: POST /leads/search debe filtrar por el parámetro `query` (texto libre),
    igual que GET /leads. Antes el controller/servicio/repositorio lo descartaban en
    silencio -- por eso el buscador del modo Tablero (que usa /leads/search) no filtraba
    nada, aunque el mismo buscador en modo Lista (GET /leads) sí funcionaba.

    Desde 2026-08-15, la búsqueda de texto libre se acotó a los campos que arman el
    título del lead (title_order IS NOT NULL) -- por eso f_nombre se crea con
    title_order=1 (ver test_search_leads_text_query_ignores_non_title_field más abajo,
    que cubre el caso contrario).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_nombre = LeadField(name="Nombre", field_type_code="STRING", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True, title_order=1)
    db_session.add(f_nombre)
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Ana Rodriguez"}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Beto Sosa"}])

    # Búsqueda de texto libre (sin filters), como manda el modo Tablero
    res = api.client.post(
        "/leads/search",
        params={"query": "rodrig"},
        json={"page": 1, "filters": []},
        headers=api.headers,
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    nombre_val = next(v for v in items[0]["field_values"] if v["field_id"] == f_nombre.id)
    assert nombre_val["value"] == "Ana Rodriguez"

    # Sin match -> vacío
    res_empty = api.client.post(
        "/leads/search",
        params={"query": "zzz_no_existe"},
        json={"page": 1, "filters": []},
        headers=api.headers,
    )
    assert res_empty.status_code == 200
    assert res_empty.json()["items"] == []

    # Combinado con un filtro estructurado (contact_state / campaign) via `filters`
    res_combo = api.client.post(
        "/leads/search",
        params={"query": "sosa", "campaign_id": camp_id},
        json={"page": 1, "filters": []},
        headers=api.headers,
    )
    assert res_combo.status_code == 200
    items_combo = res_combo.json()["items"]
    assert len(items_combo) == 1
    nombre_val_combo = next(v for v in items_combo[0]["field_values"] if v["field_id"] == f_nombre.id)
    assert nombre_val_combo["value"] == "Beto Sosa"


def test_search_leads_text_query_ignores_non_title_field(api, db_session, initial_structure):
    """
    Regresión 2026-08-15: la búsqueda de texto libre de /leads/search se acotó a los
    campos que arman el título del lead (LeadField.title_order IS NOT NULL) -- pedido
    del usuario para que el buscador no traiga resultados por coincidencias en campos
    que no se ven como "nombre" del lead (ej. una nota interna). Un campo sin
    title_order NO debe matchear, aunque el texto coincida.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_nota = LeadField(name="Nota interna", field_type_code="STRING", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)  # sin title_order
    db_session.add(f_nota)
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nota.id, "value": "Contactar por Whatsapp Rodriguez"}])

    res = api.client.post(
        "/leads/search",
        params={"query": "rodrig"},
        json={"page": 1, "filters": []},
        headers=api.headers,
    )
    assert res.status_code == 200
    assert res.json()["items"] == []

def test_search_leads_custom_field_filter_by_public_uuid(api, db_session, initial_structure):
    """
    Regresión: filtrar /leads/search por un campo custom (EAV) usando el `field_id` tal
    como lo manda el front real -- el public_uuid del LeadField, no su id interno. Antes
    esto rompía con `psycopg2.errors.InvalidTextRepresentation: invalid input syntax for
    type integer`, porque el filtro comparaba lead_field_value.field_id (entero) contra
    el UUID crudo sin resolverlo primero al id interno.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    f_nombre = LeadField(name="Nombre", field_type_code="STRING", campaign_id=camp_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add(f_nombre)
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Laura"}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_nombre.id, "value": "Martin"}])

    # Igual que manda el front: field_id = public_uuid del LeadField, no el id interno
    payload = {
        "page": 1,
        "filters": [
            {"field_id": f_nombre.public_uuid, "operator": "ilike", "value": "L"}
        ]
    }
    res = api.client.post("/leads/search", json=payload, headers=api.headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    nombre_val = next(v for v in items[0]["field_values"] if v["field_id"] == f_nombre.id)
    assert nombre_val["value"] == "Laura"

    # UUID que no corresponde a ningún LeadField -> no debe romper, solo no matchear nada
    payload_missing = {
        "page": 1,
        "filters": [
            {"field_id": "00000000-0000-0000-0000-000000000000", "operator": "ilike", "value": "L"}
        ]
    }
    res_missing = api.client.post("/leads/search", json=payload_missing, headers=api.headers)
    assert res_missing.status_code == 200
    assert res_missing.json()["items"] == []

def test_search_leads_selector_field_filter_by_public_uuid(api, db_session, initial_structure):
    """
    Regresión: filtrar /leads/search por un campo SELECTOR (nomenclador) usando el
    public_uuid de NomenclatorItem, tal como lo manda el front real (LeadFilters.tsx arma
    `value_ids` con `item.id`, que a nivel API siempre es public_uuid -- ver
    getNomenclatorItems). Mismo bug de fondo que el de field_id (public_uuid vs id interno),
    pero del lado del VALOR: los operadores eq/in del filtro EAV comparaban
    `NomenclatorItem.id` (entero) contra el uuid crudo y rompían con
    `invalid input syntax for type integer`.

    También cubre un segundo bug encontrado al escribir este test: `neq` sobre un campo
    SELECTOR devolvía siempre vacío, incluso ya resuelto el uuid -- LeadFieldValue.value
    queda NULL para campos SELECTOR (la selección real vive en la tabla M2M
    nomenclator_items), y `NULL != X` evalúa NULL en SQL, no true, así que el AND de la
    condición neq descartaba la fila siempre.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

    nom = Nomenclator(name="Prioridad Test", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    item_alta = NomenclatorItem(nomenclator_id=nom.id, value="Alta", organization_id=org_id)
    item_baja = NomenclatorItem(nomenclator_id=nom.id, value="Baja", organization_id=org_id)
    db_session.add_all([item_alta, item_baja])
    db_session.commit()

    f_prioridad = LeadField(
        name="Prioridad", field_type_code="SELECTOR", field_subtype_code="SELECTOR_SIMPLE",
        nomenclator_id=nom.id, campaign_id=camp_internal_id,
        lead_field_section_id=section_internal_id, organization_id=org_id, order=1, active=True
    )
    db_session.add(f_prioridad)
    db_session.commit()

    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_prioridad.id, "value": [item_alta.id]}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_prioridad.id, "value": [item_baja.id]}])

    # eq con public_uuid, como manda el front
    payload_eq = {
        "page": 1,
        "filters": [
            {"field_id": f_prioridad.public_uuid, "operator": "eq", "value": item_alta.public_uuid}
        ]
    }
    res_eq = api.client.post("/leads/search", json=payload_eq, headers=api.headers)
    assert res_eq.status_code == 200
    assert len(res_eq.json()["items"]) == 1

    # in con lista de public_uuid -> matchea ambos leads
    payload_in = {
        "page": 1,
        "filters": [
            {"field_id": f_prioridad.public_uuid, "operator": "in", "value": [item_alta.public_uuid, item_baja.public_uuid]}
        ]
    }
    res_in = api.client.post("/leads/search", json=payload_in, headers=api.headers)
    assert res_in.status_code == 200
    assert len(res_in.json()["items"]) == 2

    # neq con public_uuid -> antes del fix de NULL, esto devolvía siempre vacío
    payload_neq = {
        "page": 1,
        "filters": [
            {"field_id": f_prioridad.public_uuid, "operator": "neq", "value": item_alta.public_uuid}
        ]
    }
    res_neq = api.client.post("/leads/search", json=payload_neq, headers=api.headers)
    assert res_neq.status_code == 200
    items_neq = res_neq.json()["items"]
    assert len(items_neq) == 1
    val_neq = next(v for v in items_neq[0]["field_values"] if v["field_id"] == f_prioridad.id)
    assert [i["id"] for i in val_neq["nomenclator_items"]] == [item_baja.public_uuid]

    # public_uuid que no corresponde a ningún NomenclatorItem -> no debe romper, solo no matchear
    payload_missing = {
        "page": 1,
        "filters": [
            {"field_id": f_prioridad.public_uuid, "operator": "eq", "value": "00000000-0000-0000-0000-000000000000"}
        ]
    }
    res_missing = api.client.post("/leads/search", json=payload_missing, headers=api.headers)
    assert res_missing.status_code == 200
    assert res_missing.json()["items"] == []


def test_search_leads_native_fields(api, db_session, initial_structure):
    """
    Cobertura: filtrar /leads/search por cada uno de los campos nativos de Lead
    (LEAD_NATIVE_FILTER_FIELDS en lead_repository.py) usando el public_uuid tal como lo
    manda el front real. A diferencia de los campos custom (EAV, ver los dos tests de
    arriba), estos ya resuelven public_uuid -> id interno vía
    BaseRepository.resolve_fk_filter_value -- pero hasta ahora ese camino no tenía ningún
    test para /leads/search (solo para GET /leads?campaign_id=... vía query param). Cubre
    los 5 campos FK reales (campaign_id, current_state_id, contact_state_id, team_id,
    assigned_to_user_id) + un caso de fecha (created_at) + un uuid inexistente.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    state_contact_id = initial_structure["state_contact_id"]

    # LeadService.create() rechaza con 400 ("La campaña no tiene campos configurados")
    # cualquier lead -- incluso con values=[] -- si la campaña no tiene ni un LeadField
    # definido. `initial_structure` no crea ninguno (eso lo hace el fixture aparte
    # `initial_fields`, que este test no pide porque su campo "Nombre" es required=True
    # y rompería los `values=[]` de más abajo). Alcanza con un campo no-requerido.
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre", field_type_code="STRING", required=False)

    # ── campaign_id ──
    lead1 = api.create_lead(campaign_id=camp_id, values=[])
    lead2 = api.create_lead(campaign_id=camp_id, values=[])
    res_camp = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "campaign_id", "operator": "eq", "value": camp_id}]
    }, headers=api.headers)
    assert res_camp.status_code == 200
    assert len(res_camp.json()["items"]) == 2

    # ── current_state_id (Etapa) ──
    change_res = api.client.post(f"/leads/{lead2['id']}/change_state",
                                  json={"new_state_id": state_contact_id}, headers=api.headers)
    assert change_res.status_code == 200
    res_state = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "current_state_id", "operator": "eq", "value": state_contact_id}]
    }, headers=api.headers)
    assert res_state.status_code == 200
    items_state = res_state.json()["items"]
    assert len(items_state) == 1
    assert items_state[0]["id"] == lead2["id"]

    # ── contact_state_id (Estado) ──
    # LeadService.create() solo autoasigna un contact_state_id si existe un
    # LeadContactState con is_initial=True para la organización (ver lead_service.py
    # ~línea 1014) -- `initial_structure` no crea ninguno (a diferencia de LeadState,
    # que sí trae 3 vía ese fixture), así que sin esto lead3["contact_state"] queda None.
    # Necesitamos al menos 2: uno inicial (auto-asignado al crear el lead) y otro
    # distinto para poder elegir un "target_cs" real más abajo (next(... != current_cs_id)).
    db_session.add(LeadContactState(name="Nuevo", organization_id=org_id, is_initial=True, order=1))
    db_session.add(LeadContactState(name="Contactado", organization_id=org_id, is_initial=False, order=2))
    db_session.commit()

    lead3 = api.create_lead(campaign_id=camp_id, values=[])
    current_cs_id = lead3["contact_state"]["id"]
    contact_states = api.client.get("/lead_contact_states/", headers=api.headers).json()["items"]
    target_cs = next(cs for cs in contact_states if cs["id"] != current_cs_id)
    change_cs_res = api.client.post(f"/leads/{lead3['id']}/change_contact_state",
                                     json={"new_contact_state_id": target_cs["id"]}, headers=api.headers)
    assert change_cs_res.status_code == 200
    res_cs = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "contact_state_id", "operator": "eq", "value": target_cs["id"]}]
    }, headers=api.headers)
    assert res_cs.status_code == 200
    items_cs = res_cs.json()["items"]
    assert len(items_cs) == 1
    assert items_cs[0]["id"] == lead3["id"]

    # ── team_id ──
    team = Team(name="Equipo Filtro Test", organization_id=org_id)
    db_session.add(team)
    db_session.commit()

    lead4 = api.create_lead(campaign_id=camp_id, values=[])
    api.bulk_assign(lead_ids=[lead4["id"]], target_team_id=team.public_uuid)
    res_team = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "team_id", "operator": "eq", "value": team.public_uuid}]
    }, headers=api.headers)
    assert res_team.status_code == 200
    items_team = res_team.json()["items"]
    assert len(items_team) == 1
    assert items_team[0]["id"] == lead4["id"]

    # uuid de team inexistente -> no debe romper, solo no matchear (mismo criterio que field_id)
    res_team_missing = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "team_id", "operator": "eq", "value": "00000000-0000-0000-0000-000000000000"}]
    }, headers=api.headers)
    assert res_team_missing.status_code == 200
    assert res_team_missing.json()["items"] == []

    # ── assigned_to_user_id ──
    user = User(name="Asignado Filtro", last_name="Test", email=f"asignado_filtro_{org_id}@test.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserOrganization(user_id=user.id, organization_id=org_id, active=True))
    db_session.commit()

    lead5 = api.create_lead(campaign_id=camp_id, values=[])
    api.bulk_assign(lead_ids=[lead5["id"]], target_user_id=user.public_uuid)
    res_user = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "assigned_to_user_id", "operator": "eq", "value": user.public_uuid}]
    }, headers=api.headers)
    assert res_user.status_code == 200
    items_user = res_user.json()["items"]
    assert len(items_user) == 1
    assert items_user[0]["id"] == lead5["id"]

    # ── created_at (fecha, no es FK -- cubre el paso por resolve_fk_filter_value sin romper) ──
    res_created_future = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "created_at", "operator": "gte", "value": "2099-01-01T00:00:00"}]
    }, headers=api.headers)
    assert res_created_future.status_code == 200
    assert res_created_future.json()["items"] == []

    res_created_past = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "created_at", "operator": "gte", "value": "2000-01-01T00:00:00"}]
    }, headers=api.headers)
    assert res_created_past.status_code == 200
    assert len(res_created_past.json()["items"]) >= 5


def test_search_leads_created_by_updated_by(api, db_session, initial_structure):
    """
    Bug real encontrado 2026-08-10 (reportado por el usuario -- filtro "Usuario Modificador"
    del sidebar no traía resultados existiendo leads modificados por ese usuario):
    created_by/updated_by quedaban afuera de LEAD_NATIVE_FILTER_FIELDS ("no incluir campos
    sensibles de infraestructura"), pero el frontend sí los expone como filtros nativos
    (nativeLeadFields.ts ids -7/-8, "Usuario Creador"/"Usuario Modificador"). Al no estar en
    el set, el field_id ("created_by"/"updated_by") no entraba por la rama de filtros nativos
    y caía por descarte en la rama de filtros EAV/custom (para campos LeadField), donde nunca
    matcheaba ningún LeadField real -> _resolve_custom_field_id devolvía el sentinel -1 y el
    filtro daba SIEMPRE 0 resultados, sin importar los leads que hubiera. Cubre que ahora
    resuelven como cualquier otra FK nativa (resolve_fk_filter_value), igual que
    assigned_to_user_id en el test de arriba.
    """
    camp_id = initial_structure["campaign_id"]
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre", field_type_code="STRING", required=False)

    # Mismo usuario hardcodeado que devuelve override_get_current_user (tests/fixtures/client.py)
    # para todas las requests hechas con el fixture `api`.
    creator = db_session.query(User).filter_by(email="francoruiz.admin@crm.com").first()
    assert creator is not None

    lead = api.create_lead(campaign_id=camp_id, values=[])

    # ── created_by ──
    res_created_by = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "created_by", "operator": "eq", "value": creator.public_uuid}]
    }, headers=api.headers)
    assert res_created_by.status_code == 200
    items_created_by = res_created_by.json()["items"]
    assert len(items_created_by) >= 1
    assert any(item["id"] == lead["id"] for item in items_created_by)

    # uuid inexistente -> no debe romper, solo no matchear (mismo criterio que team_id)
    res_created_by_missing = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "created_by", "operator": "eq", "value": "00000000-0000-0000-0000-000000000000"}]
    }, headers=api.headers)
    assert res_created_by_missing.status_code == 200
    assert res_created_by_missing.json()["items"] == []

    # ── updated_by ──
    # update_lead() con values=[] y sin contact_state_id/tag_ids termina con lead_data={}
    # en LeadService.update() (obj_in.model_dump(exclude_unset=True, exclude={"values",
    # "tag_ids"})) -- cls.repository.update() ni se llama, así que updated_by queda NULL.
    # change_contact_state sí dispara un cls.repository.update() real (contact_state_id
    # cambia de verdad), que es lo que efectivamente pisa updated_by (BaseRepository.update,
    # línea ~570: "if updated_by is not None ... data['updated_by'] = updated_by").
    org_id = initial_structure["org_id"]
    db_session.add(LeadContactState(name="Nuevo UB", organization_id=org_id, is_initial=True, order=1))
    db_session.add(LeadContactState(name="Contactado UB", organization_id=org_id, is_initial=False, order=2))
    db_session.commit()

    lead_ub = api.create_lead(campaign_id=camp_id, values=[])
    current_cs_id = lead_ub["contact_state"]["id"]
    contact_states = api.client.get("/lead_contact_states/", headers=api.headers).json()["items"]
    target_cs = next(cs for cs in contact_states if cs["id"] != current_cs_id)
    change_cs_res = api.client.post(f"/leads/{lead_ub['id']}/change_contact_state",
                                     json={"new_contact_state_id": target_cs["id"]}, headers=api.headers)
    assert change_cs_res.status_code == 200

    res_updated_by = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "updated_by", "operator": "eq", "value": creator.public_uuid}]
    }, headers=api.headers)
    assert res_updated_by.status_code == 200
    items_updated_by = res_updated_by.json()["items"]
    assert len(items_updated_by) >= 1
    assert any(item["id"] == lead_ub["id"] for item in items_updated_by)

    # uuid inexistente -> tampoco debe romper acá
    res_updated_by_missing = api.client.post("/leads/search", json={
        "page": 1, "filters": [{"field_id": "updated_by", "operator": "eq", "value": "00000000-0000-0000-0000-000000000000"}]
    }, headers=api.headers)
    assert res_updated_by_missing.status_code == 200
    assert res_updated_by_missing.json()["items"] == []


# --- TESTS DE ORDENAMIENTO (order_by) ---
#
# Bug real encontrado 2026-08-11 (reportado por el usuario): LeadRepository._apply_dynamic_ordering
# solo reconocía `order_by` como id de LeadField si era un string 100% numérico. El front
# (LeadTablePresentation.tsx::orderKey) manda el public_uuid del LeadField para cualquier columna
# custom -- un uuid nunca pasa `.isdigit()`, así que ordenar por una columna custom caía SIEMPRE
# al fallback (id DESC), sin ningún error. Estos tests cubren el fix (resolución uuid -> id
# interno) tanto en GET /leads como en POST /leads/search (comparten el mismo helper), además del
# caso nativo (que ya funcionaba, para no perder cobertura) y el fallback ante un valor inválido.

def _value_for_field(lead: dict, field_uuid: str):
    """Extrae el valor de un campo custom de la respuesta de un lead (LeadResponse.field_values)."""
    for fv in lead.get("field_values", []):
        field = fv.get("field") or {}
        if field.get("id") == field_uuid:
            return fv.get("value")
    return None


class TestLeadOrdering:
    def _setup_leads_with_custom_field(self, api, camp_id):
        """Crea un campo STRING y 3 leads con valores distintos, fuera de orden alfabético
        y fuera de orden de creación, para poder distinguir "orden real" de "orden por id"."""
        field = api.create_lead_field(campaign_id=camp_id, name="Nombre Orden", field_type_code="STRING")
        field_uuid = field["id"]

        lead_charlie = api.create_lead(campaign_id=camp_id, values=[{"field_id": field_uuid, "value": "Charlie"}])
        lead_alice = api.create_lead(campaign_id=camp_id, values=[{"field_id": field_uuid, "value": "Alice"}])
        lead_bob = api.create_lead(campaign_id=camp_id, values=[{"field_id": field_uuid, "value": "Bob"}])

        return field_uuid, [lead_charlie, lead_alice, lead_bob]

    def test_get_leads_order_by_custom_field_uuid_ascending(self, api, initial_structure):
        """GET /leads?order_by=<uuid de LeadField> -- antes del fix, esto caía siempre al
        fallback (id DESC) sin importar qué se pidiera."""
        camp_id = initial_structure["campaign_id"]
        field_uuid, _ = self._setup_leads_with_custom_field(api, camp_id)

        resp = api.client.get(
            f"/leads?campaign_id={camp_id}&order_by={field_uuid}&ascending=true",
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        values = [_value_for_field(item, field_uuid) for item in items]
        assert values == ["Alice", "Bob", "Charlie"]

    def test_get_leads_order_by_custom_field_uuid_descending(self, api, initial_structure):
        camp_id = initial_structure["campaign_id"]
        field_uuid, _ = self._setup_leads_with_custom_field(api, camp_id)

        resp = api.client.get(
            f"/leads?campaign_id={camp_id}&order_by={field_uuid}&ascending=false",
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        values = [_value_for_field(item, field_uuid) for item in items]
        assert values == ["Charlie", "Bob", "Alice"]

    def test_search_leads_order_by_custom_field_uuid(self, api, initial_structure):
        """Mismo fix, pero por el otro endpoint (POST /leads/search) -- comparten
        _apply_dynamic_ordering, así que antes del fix tenía el mismo bug."""
        camp_id = initial_structure["campaign_id"]
        field_uuid, _ = self._setup_leads_with_custom_field(api, camp_id)

        resp = api.client.post(
            "/leads/search",
            json={"page": 1, "filters": []},
            params={"order_by": field_uuid, "ascending": "true"},
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        values = [_value_for_field(item, field_uuid) for item in items]
        assert values == ["Alice", "Bob", "Charlie"]

    def test_get_leads_order_by_native_field_respects_direction(self, api, initial_structure):
        """Caso que ya funcionaba (campo nativo real, ej. id) -- lo cubrimos para no perder
        esta rama al tocar _apply_dynamic_ordering. También valida el fix del desempate:
        ascending=False debe dar exactamente el orden inverso de ascending=True."""
        camp_id = initial_structure["campaign_id"]
        # LeadService.create() rechaza con 400 cualquier lead si la campaña no tiene ni un
        # LeadField configurado (ver test_search_leads_native_fields más arriba).
        api.create_lead_field(campaign_id=camp_id, name="Campo Libre", field_type_code="STRING", required=False)
        lead_a = api.create_lead(campaign_id=camp_id, values=[])
        lead_b = api.create_lead(campaign_id=camp_id, values=[])
        lead_c = api.create_lead(campaign_id=camp_id, values=[])

        resp_asc = api.client.get(
            f"/leads?campaign_id={camp_id}&order_by=id&ascending=true", headers=api.headers
        )
        assert resp_asc.status_code == 200, resp_asc.text
        ids_asc = [item["id"] for item in resp_asc.json()["items"]]

        resp_desc = api.client.get(
            f"/leads?campaign_id={camp_id}&order_by=id&ascending=false", headers=api.headers
        )
        assert resp_desc.status_code == 200, resp_desc.text
        ids_desc = [item["id"] for item in resp_desc.json()["items"]]

        assert ids_asc == list(reversed(ids_desc))
        assert ids_asc.index(lead_a["id"]) < ids_asc.index(lead_b["id"]) < ids_asc.index(lead_c["id"])

    def test_get_leads_order_by_unknown_value_falls_back_without_error(self, api, initial_structure):
        """Un order_by que no matchea ninguna columna real ni ningún LeadField (uuid
        inexistente) no debe romper -- debe caer al fallback (id DESC) en silencio,
        mismo criterio que el resto de la app ante FKs no encontradas."""
        camp_id = initial_structure["campaign_id"]
        api.create_lead_field(campaign_id=camp_id, name="Campo Libre", field_type_code="STRING", required=False)
        api.create_lead(campaign_id=camp_id, values=[])

        resp = api.client.get(
            f"/leads?campaign_id={camp_id}&order_by=00000000-0000-0000-0000-000000000000",
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) >= 1


# --- TESTS AVANZADOS (NOMENCLADORES) ---

def test_create_lead_with_multiple_nomenclator(api, db_session, initial_structure):
    """
    Este es el TEST CLAVE para validar tu refactorización Many-to-Many.
    Crea un campo 'Etiquetas' (Multiple) y le asigna 2 valores.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    # 1. Setup Datos Específicos para este test (Nomenclador y Items)
    nom = Nomenclator(name="Etiquetas Test", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    
    item1 = NomenclatorItem(nomenclator_id=nom.id, value="Urgente", organization_id=org_id)
    item2 = NomenclatorItem(nomenclator_id=nom.id, value="VIP", organization_id=org_id)
    item3 = NomenclatorItem(nomenclator_id=nom.id, value="Descartado", organization_id=org_id)
    db_session.add_all([item1, item2, item3])
    db_session.commit() # Commit para tener IDs disponibles

    field_tags = LeadField(
        name="Etiquetas",
        campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        field_type_code="SELECTOR",
        field_subtype_code="SELECTOR_MULTIPLE",
        nomenclator_id=nom.id,
        lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id),
        required=False,
        order=5,
        organization_id=org_id,
        active=True
    )
    db_session.add(field_tags)
    db_session.commit()

    # 3. Payload: Enviamos LISTA de IDs [item1, item2] usando api helper
    values = [{"field_id": field_tags.id, "value": [item1.id, item2.id]}]
    data = api.create_lead(campaign_id=camp_id, values=values, expected_status=200)
    
    # 4. Validar que la respuesta traiga la lista de objetos expandida
    val_tags = next((v for v in data["field_values"] if v["field_id"] == field_tags.id), None)
    
    assert val_tags is not None
    # Verificamos que 'nomenclator_items' sea una lista con 2 elementos
    assert "nomenclator_items" in val_tags
    assert len(val_tags["nomenclator_items"]) == 2
    
    # Verificar contenido
    nombres = [item["value"] for item in val_tags["nomenclator_items"]]
    assert "Urgente" in nombres
    assert "VIP" in nombres
    assert "Descartado" not in nombres


def test_search_lead_by_nomenclator(api, db_session, initial_structure):
    """
    Prueba el repositorio de búsqueda con la lógica OR (value text OR relation items).
    Busca leads que tengan la etiqueta 'Ventas'.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    # 1. Setup Nomenclador
    nom = Nomenclator(name="Depto", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    item_ventas = NomenclatorItem(nomenclator_id=nom.id, value="Ventas", organization_id=org_id)
    item_it = NomenclatorItem(nomenclator_id=nom.id, value="IT", organization_id=org_id)
    db_session.add_all([item_ventas, item_it])
    db_session.commit()

    field_depto = LeadField(
        name="Departamento", campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        field_type_code="SELECTOR", field_subtype_code="SELECTOR_SIMPLE",
        nomenclator_id=nom.id, lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id), order=1,
        organization_id=org_id, active=True
    )
    db_session.add(field_depto)
    db_session.commit()

    # 3. Crear Leads
    api.create_lead(campaign_id=camp_id, values=[{"field_id": field_depto.id, "value": item_ventas.id}])
    api.create_lead(campaign_id=camp_id, values=[{"field_id": field_depto.id, "value": item_it.id}])

    # 4. BUSCAR: Filtramos por ID de Ventas
    search_payload = {
        "page": 1,
        "page_size": 10,
        "filters": [
            {
                "field_id": field_depto.id,
                "operator": "eq", 
                "value": item_ventas.id
            }
        ]
    }
    
    response = api.client.post("/leads/search", json=search_payload, headers=api.headers)
    assert response.status_code == 200
    
    data = response.json()
    items = data.get("items", data)
    
    # Debe encontrar solo 1 (El de Ventas)
    assert len(items) == 1
    
    # Verificamos que sea el correcto
    vals = items[0]["field_values"]
    target_val = next(v for v in vals if v["field_id"] == field_depto.id)
    assert target_val["nomenclator_items"][0]["value"] == "Ventas"


def test_create_field_from_template(api, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (POSTAL_CODE) y verifica que:
    1. Se cree el campo correctamente con las propiedades de la plantilla.
    """
    camp_id = initial_structure["campaign_id"]
    
    field_data = api.create_lead_field_from_template(
        campaign_id=camp_id, template_code="POSTAL_CODE", required=True, expected_status=200
    )

    # detailed=true: GET_ONE default (LeadFieldResponse) no incluye validation_rules,
    # solo LeadFieldDetailedResponse lo trae.
    field_created = api.client.get(f"/lead_fields/{field_data['id']}?detailed=true", headers=api.headers)
    assert field_created.status_code == 200
    assert field_created.json()["validation_rules"] is not None


def test_create_field_from_template_and_validate_success(api, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (DNI_ARG) y verifica que:
    1. Se cree el campo correctamente.
    2. Se genere automáticamente una regla de validación.
    3. El sistema acepte valores que cumplan esa regla.
    """
    camp_id = initial_structure["campaign_id"]
    
    field_data = api.create_lead_field_from_template(
        campaign_id=camp_id, template_code="DNI_ARG", required=True, expected_status=200
    )
    field_id = field_data["id"]
    
    # 4. Validar: Intentar crear Lead con DNI VÁLIDO
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": field_id, "value": "46378765"}], 
        expected_status=200
    )


def test_create_field_from_template_and_validate_failure(api, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (DNI_ARG) y verifica que:
    1. Se cree el campo correctamente.
    2. Se genere automáticamente una regla de validación.
    3. El sistema rechace valores que no cumplan esa regla (Dni inválido).
    """
    camp_id = initial_structure["campaign_id"]
    
    field_data = api.create_lead_field_from_template(
        campaign_id=camp_id, template_code="DNI_ARG", required=True, expected_status=200
    )
    field_id = field_data["id"]

    # 3. Validar: Intentar crear Lead con DNI INVÁLIDO
    res_fail = api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": field_id, "value": "32323DAD"}], 
        expected_status=False
    )
    
    assert res_fail.status_code == 400
    assert "números" in res_fail.text.lower() or "exceder" in res_fail.text.lower()


def test_get_leads_filtering(api, db_session, initial_structure):
    """
    Valida los filtros de listado:
    - campaign_id (Aislamiento entre campañas)
    """
    camp_a_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    workspace_id = initial_structure["workspace_id"]
    lead_flow_id = initial_structure["lead_flow_id"]
    section_id = initial_structure["section_id"]

    # workspace_id/lead_flow_id/section_id llegan como public_uuid (Fase 3); Campaign/
    # LeadState/LeadField construidos crudos acá necesitan el id interno.
    workspace_internal_id = _resolve_internal_id(db_session, Workspace, workspace_id)
    lead_flow_internal_id = _resolve_internal_id(db_session, LeadFlow, lead_flow_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)
    camp_a_internal_id = _resolve_internal_id(db_session, Campaign, camp_a_id)

    camp_b = Campaign(name="Campaña B", workspace_id=workspace_internal_id, lead_flow_id=lead_flow_internal_id, organization_id=org_id)
    db_session.add(camp_b)
    db_session.flush()

    # --- Inyectar estado inicial a la campaña extra ---
    state_extra = LeadState(
        lead_flow_id=lead_flow_internal_id, organization_id=org_id,
        name="Nuevo Extra", category="OPEN", is_initial=True, order=1
    )
    db_session.add(state_extra)

    f_nom_a = LeadField(name="Nombre A", field_type_code="STRING", campaign_id=camp_a_internal_id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    f_nom_b = LeadField(name="Nombre B", field_type_code="STRING", campaign_id=camp_b.id, order=1, lead_field_section_id=section_internal_id, organization_id=org_id, active=True)
    db_session.add_all([f_nom_a, f_nom_b])
    db_session.commit()

    # 1. Crear Leads en Campaña A
    api.create_lead(campaign_id=camp_a_id, values=[{"field_id": f_nom_a.id, "value": "Lead A1"}])
    api.create_lead(campaign_id=camp_a_id, values=[{"field_id": f_nom_a.id, "value": "Lead A2"}])

    # 2. Crear Lead en Campaña B -- campaign_id en el body de create_lead es str (public_uuid)
    api.create_lead(campaign_id=camp_b.public_uuid, values=[{"field_id": f_nom_b.id, "value": "Lead B1"}])

    # --- TEST DE FILTROS ---
    # Caso 1: Campaña A
    res_active = api.client.get(f"/leads/?campaign_id={camp_a_id}", headers=api.headers)
    items_active = res_active.json().get("items", res_active.json())
    assert len(items_active) == 2

    # Caso 2: Filtrar por Campaña B
    res_b = api.client.get(f"/leads/?campaign_id={camp_b.id}", headers=api.headers)
    items_b = res_b.json().get("items", res_b.json())
    assert len(items_b) == 1
    
    val_b1 = next(v for v in items_b[0]["field_values"] if v["field_id"] == f_nom_b.id)
    assert val_b1["value"] == "Lead B1"


def test_create_lead_int_validation_case_of_decimal(api, db_session, initial_structure):
    """
    Caso 3: Validación estricta de Integers.
    - Rechazar decimales (10.5).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f_int = LeadField(name="Contador", field_type_code="INT", campaign_id=_resolve_internal_id(db_session, Campaign, camp_id), order=1, lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id), organization_id=org_id, active=True)
    db_session.add(f_int)
    db_session.commit()

    # --- Sub-caso 3.1: Decimales ---
    res_decimal = api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_int.id, "value": 10.5}], 
        expected_status=False
    )
    
    assert res_decimal.status_code in [400, 422]
    assert "espera" in res_decimal.text.lower()


def test_create_lead_int_validation_case_of_huge_int(api, db_session, initial_structure):
    """
    Caso 3: Validación estricta de Integers.
    - Manejar Overflow (Números gigantes).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    f_int = LeadField(name="Contador", field_type_code="INT", campaign_id=_resolve_internal_id(db_session, Campaign, camp_id), order=1, lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id), organization_id=org_id, active=True)
    db_session.add(f_int)
    db_session.commit()

    # --- Sub-caso 3.2: Integer Overflow ---
    huge_number = 99999999999999999999999  
    
    res_overflow = api.create_lead(
        campaign_id=camp_id,
        values=[{"field_id": f_int.id, "value": huge_number}],
        expected_status=False
    )

    assert res_overflow.status_code == 200
    assert res_overflow.status_code != 500, "Ojo: El error de Overflow no fue capturado y generó un 500."


def test_bulk_assign_sets_updated_by(api, db_session, initial_structure):
    """
    Bug real encontrado 2026-08-11 (reportado por Franco: "Modificado por" no se actualizaba
    al reasignar equipo/usuario asignado). bulk_assign() cambiaba team_id/assigned_to_user_id
    directo con setattr, sin pasar por repository.update() (el único lugar que graba
    updated_by) -- confirmado con este mismo test antes del fix, `updater` quedaba en None.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre Updated By", field_type_code="STRING", required=False)
    team_a = Team(name="Equipo Updated By", organization_id=org_id)
    db_session.add(team_a)
    db_session.commit()

    lead = api.create_lead(campaign_id=camp_id, values=[])
    assert lead.get("updater") is None

    api.bulk_assign(lead_ids=[lead["id"]], target_team_id=team_a.public_uuid)

    fetched = api.get_lead(lead["id"])
    # No comparamos updated_at contra created_at: dentro de la misma transacción de test,
    # Postgres resuelve func.now() al inicio de la transacción (no por statement), así que
    # ambos timestamps coinciden aunque el UPDATE sí haya ocurrido -- lo que de verdad prueba
    # el fix es que updater (antes siempre None en este flujo) ahora esté poblado.
    assert fetched.get("updater") is not None


def test_tag_only_update_sets_updated_by(api, initial_structure):
    """
    Mismo bug que test_bulk_assign_sets_updated_by, otro flujo: PUT /leads/{id} con solo
    tag_ids (sin ningún otro campo) deja lead_data vacío en LeadService.update(), así que se
    saltea el repository.update() que graba updated_by -- _assign_tags solo toca la relación
    M2M lead.tags, no una columna del lead.
    """
    camp_id = initial_structure["campaign_id"]
    api.create_lead_field(campaign_id=camp_id, name="Campo Libre Tag Updated By", field_type_code="STRING", required=False)
    lead = api.create_lead(campaign_id=camp_id, values=[])
    assert lead.get("updater") is None

    tag_resp = api.client.post("/tags", json={"name": "Tag Updated By", "color": "#123456"}, headers=api.headers)
    assert tag_resp.status_code in (200, 201), tag_resp.text
    tag = tag_resp.json()

    resp = api.client.put(f"/leads/{lead['id']}", json={"campaign_id": camp_id, "tag_ids": [tag["id"]]}, headers=api.headers)
    assert resp.status_code == 200, resp.text

    fetched = api.get_lead(lead["id"])
    assert fetched.get("updater") is not None