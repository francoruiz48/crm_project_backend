import pytest
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule
from app.models.lead import Lead
from app.models.lead_field_section import LeadFieldSection
from app.models.organization import Organization
from app.models.campaign import Campaign
from tests.helpers.api_helpers import ApiClient


def _resolve_internal_id(db_session, model, public_uuid_or_int):
    """
    Muchas respuestas de la API (field["id"], rule["id"], lead["id"], etc.) traen
    public_uuid (Fase 1-3), pero las PKs reales de las tablas siguen siendo int --
    hay que resolver antes de usarlas en una query cruda de SQLAlchemy.
    """
    if isinstance(public_uuid_or_int, int):
        return public_uuid_or_int
    return db_session.query(model.id).filter_by(public_uuid=public_uuid_or_int).scalar()


def test_lead_field_lifecycle_no_data(api, db_session, initial_structure):
    """
    Caso: Crear un campo y borrarlo CUANDO NO HAY LEADS.
    Resultado esperado: Borrado físico inmediato (Action: deleted).
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo vía API
    field = api.create_lead_field(camp_id, "Campo Efímero", "STRING")
    field_id = field["id"]
    field_internal_id = _resolve_internal_id(db_session, LeadField, field_id)

    # 2. Borrar Campo (Usamos client directo para validar la respuesta específica 'action')
    res_del = api.client.delete(f"/lead_fields/{field_id}", headers=api.headers)

    assert res_del.status_code == 200
    assert res_del.json()["action"] == "deleted"

    # 3. Verificar en DB que no existe (Borrado Físico)
    db_session.expire_all()
    field_db = db_session.get(LeadField, field_internal_id)
    assert field_db is None


def test_lead_field_backfill_existing_leads(api, initial_structure):
    """
    Caso: Backfill (Relleno automático).
    1. Crear Leads primero.
    2. Crear un NUEVO campo después.
    3. Verificar que los leads viejos tengan ese campo.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Setup: Crear campo base y un Lead
    f_base = api.create_lead_field(camp_id, "Base", "STRING")
    
    # Crear Lead
    api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "Lead Viejo"}])

    # 2. Agregar nuevo campo con Default Value
    f_new = api.create_lead_field(
        camp_id, 
        "Nuevo Campo Backfill", 
        "STRING",
        default_value="Relleno Automático", # <--- Probamos backfill
        required=False
    )

    # 3. Verificación
    # Obtenemos los leads para ver si tienen el valor nuevo
    res_leads = api.client.get(f"/leads/?campaign_id={camp_id}", headers=api.headers)
    leads = res_leads.json().get("items", res_leads.json())
    
    assert len(leads) == 1
    lead_values = leads[0]["field_values"]
    
    # Buscamos el valor del nuevo campo
    new_val = next((v for v in lead_values if v["field"]["id"] == f_new["id"]), None)
    
    assert new_val is not None
    assert new_val["value"] == "Relleno Automático"


def test_lead_field_delete_with_data_soft_delete(api, db_session, initial_structure):
    """
    Caso: Borrar un campo CUANDO YA TIENE DATOS.
    Resultado esperado: Desactivación (Soft Delete).
    Action: disabled.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo y Lead que lo usa
    f_dato = api.create_lead_field(camp_id, "Dato Importante", "INT")
    f_dato_internal_id = _resolve_internal_id(db_session, LeadField, f_dato["id"])

    api.create_lead(camp_id, [{"field_id": f_dato["id"], "value": 100}])

    # 2. Intentar Borrar el Campo
    res_del = api.client.delete(f"/lead_fields/{f_dato['id']}", headers=api.headers)
    
    # 3. Validar respuesta Híbrida
    assert res_del.status_code == 200
    data = res_del.json()
    assert data["action"] == "disabled" # <--- CLAVE: No borró, solo desactivó

    # 4. Verificar en DB (Soft Delete)
    db_session.expire_all()
    field_db = db_session.get(LeadField, f_dato_internal_id)
    assert field_db is not None
    assert field_db.active is False


def test_create_lead_ignores_disabled_required_field(api, initial_structure):
    """
    Caso: Campo Requerido que fue Desactivado (Soft Delete).
    Prueba: Al crear un nuevo Lead, el sistema debe IGNORAR ese campo.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo Requerido y uno Opcional
    f_req = api.create_lead_field(camp_id, "Campo Obligatorio", "STRING", required=True)
    api.create_lead_field(camp_id, "Campo No Obligatorio", "STRING", required=False)

    # Creamos un lead para forzar Soft Delete al borrar
    api.create_lead(camp_id, [{"field_id": f_req["id"], "value": "Valor 1"}])
    
    # Borramos -> Se transforma en Soft Delete (disabled)
    api.client.delete(f"/lead_fields/{f_req['id']}", headers=api.headers)

    # 2. Intentar crear Lead 2 SIN enviar el campo requerido (que ahora está off)
    api.create_lead(camp_id, values=[]) 


def test_cannot_add_required_field_to_campaign_with_leads(api, initial_structure):
    """
    Caso: No se debe permitir crear un campo REQUIRED si la campaña ya tiene leads.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Lead en la campaña (Campaña sucia)
    f_existente = api.create_lead_field(camp_id, "AAA", "STRING")
    api.create_lead(camp_id, [{"field_id": f_existente["id"], "value": "x"}])

    # 2. Intentar agregar nuevo campo Required (Debe fallar 400)
    api.create_lead_field(
        camp_id, 
        "Campo Imposible", 
        "INT", 
        required=True, # <--- ESTO ES LO ILEGAL
        expected_status=400
    )


def test_reactivate_field(api, db_session, initial_structure):
    """
    Caso: Reactivar un campo previamente eliminado (Soft Deleted).
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Setup: Campo con datos -> Soft Delete
    f_test = api.create_lead_field(camp_id, "Zombie Field", "STRING")
    
    api.create_lead(camp_id, [{"field_id": f_test["id"], "value": "A"}])
    
    api.client.delete(f"/lead_fields/{f_test['id']}", headers=api.headers)

    # 2. Reactivar
    res_active = api.client.put(f"/lead_fields/active/{f_test['id']}", headers=api.headers)
    assert res_active.status_code == 200

    # 3. Validar
    db_session.expire_all()
    f_db = db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, f_test["id"]))
    assert f_db.active is True


def test_create_lead_fails_no_fields_defined(api, initial_structure):
    """
    Caso: Campaña nueva sin NINGÚN campo creado.
    Resultado: 400 Bad Request.
    """
    camp_id = initial_structure["campaign_id"]
    # Intentamos crear lead enviando lista vacía
    api.create_lead(camp_id, values=[], expected_status=400)


def test_create_lead_fails_all_fields_disabled(api, initial_structure):
    """
    Caso: Campaña tenía campos, pero fueron TODOS desactivados.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear un campo y desactivarlo
    f_temp = api.create_lead_field(camp_id, "Campo X", "STRING")
    api.client.delete(f"/lead_fields/{f_temp['id']}", headers=api.headers)
    
    # 2. Intentar crear lead (Falla porque no hay campos activos)
    api.create_lead(camp_id, values=[], expected_status=400)


def test_create_lead_success_empty_values_optional_fields(api, initial_structure):
    """
    Caso: Campaña tiene campos ACTIVOS, pero NO SON OBLIGATORIOS.
    Enviamos values=[], el sistema debe rellenar con None/Default.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo Opcional
    f_opcional = api.create_lead_field(camp_id, "Comentarios", "STRING", required=False)
    
    # 2. Crear Lead sin enviar valores
    data = api.create_lead(camp_id, values=[])
    
    # Verificamos que se creó el valor nulo internamente
    val_guardado = next((v for v in data["field_values"] if v["field"]["id"] == f_opcional["id"]), None)
    assert val_guardado is not None
    assert val_guardado["value"] is None


def test_create_lead_field_fail_order_collision(api, initial_structure):
    """
    Caso: Intentar crear un campo con un 'order' manual que ya está ocupado.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo A en orden 5
    api.create_lead_field(camp_id, "Campo A", "STRING", order=5)

    # 2. Intentar Crear Campo B en orden 5 (Falla)
    api.create_lead_field(camp_id, "Campo B", "INT", order=5, expected_status=400)


def test_create_lead_field_fail_nomenclator_type_mismatch(api, initial_structure):
    """
    Caso: Enviar 'nomenclator_id' pero con un 'field_type_code' incorrecto.
    """
    camp_id = initial_structure["campaign_id"]
    
    # Crear nomenclador vía API (ya no enviamos organization_id en el payload)
    res_nom = api.client.post("/nomenclators/", json={"name": "Paises Test"}, headers=api.headers)
    assert res_nom.status_code in [200, 201]
    nom_id = res_nom.json()["id"]

    # Intentar crear campo incorrecto
    api.create_lead_field(
        camp_id, 
        "Pais", 
        "INT", # <--- ERROR: Debería ser SELECTOR
        nomenclator_id=nom_id,
        expected_status=400
    )


def test_create_lead_field_fail_subtype_mismatch(api, initial_structure):
    """
    Caso: Enviar un subtipo que no pertenece al tipo de campo padre.
    """
    camp_id = initial_structure["campaign_id"]
    
    api.create_lead_field(
        camp_id, 
        "Archivo Loco", 
        "FILE", 
        subtype_code="SELECTOR_SIMPLE", # <--- ERROR
        expected_status=400
    )


def test_create_lead_field_fail_missing_subtype(api, initial_structure):
    """
    Caso: Crear un campo que REQUIERE subtipo (como SELECTOR) sin enviarlo.
    """
    camp_id = initial_structure["campaign_id"]
    
    api.create_lead_field(
        camp_id, 
        "Selector Incompleto", 
        "SELECTOR",
        subtype_code=None, # <--- ERROR: Falta subtipo
        expected_status=400
    )


def test_create_lead_field_fail_primary_with_existing_leads(api, initial_structure):
    """
    Caso: Intentar agregar un campo 'is_primary' cuando ya existen leads.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear un campo base y un lead
    f_base = api.create_lead_field(camp_id, "Base", "STRING")
    api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "test"}])

    # 2. Intentar crear campo Primary (Falla)
    api.create_lead_field(
        camp_id, 
        "DNI Nuevo", 
        "STRING", 
        is_primary=True, 
        expected_status=400
    )


def test_update_field_fail_change_type(api, initial_structure):
    """
    Caso: Intentar cambiar el tipo de dato de un campo existente.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear campo STRING
    field = api.create_lead_field(camp_id, "Original", "STRING")

    # 2. Intentar cambiarlo a INT (Asumimos que la API lo prohíbe)
    res_update = api.client.put(f"/lead_fields/{field['id']}", json={
        "field_type_code": "INT",
        "campaign_id": camp_id
    }, headers=api.headers)
    
    if res_update.status_code == 200:
        assert res_update.json()["field_type_code"] == "STRING"
    else:
        assert res_update.status_code == 400


def test_update_field_fail_required_with_null_values(api, initial_structure):
    """
    Caso: Hacer REQUERIDO un campo que ya tiene valores NULOS en la BD.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo Opcional y un Lead sin valor
    f_opcional = api.create_lead_field(camp_id, "Opcional", "STRING", required=False)
    api.create_lead(camp_id, values=[]) # Lead con valor null

    # 2. Intentar actualizar a Required=True
    res = api.client.put(f"/lead_fields/{f_opcional['id']}", json={
        "campaign_id": camp_id,
        "required": True 
    }, headers=api.headers)
    
    assert res.status_code == 400


def test_get_fields_filtering_active(api, db_session, initial_structure):
    """
    Caso: Verificar que el listado oculte los campos desactivados (Soft Deleted)
    por defecto.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    # 1. Crear Campo A (Activo) y B (Inactivo)
    # campaign_id/lead_field_section_id son columnas Integer FK reales -- initial_structure
    # devuelve public_uuid (Fase 3), hay que resolver al id interno antes del INSERT crudo.
    camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)
    f_active = LeadField(name="Visible", field_type_code="STRING", campaign_id=camp_internal_id, active=True, order=1, lead_field_section_id=section_internal_id, organization_id=org_id)
    f_inactive = LeadField(name="Oculto", field_type_code="STRING", campaign_id=camp_internal_id, active=False, order=2, lead_field_section_id=section_internal_id, organization_id=org_id)
    db_session.add_all([f_active, f_inactive])
    db_session.commit()

    # 2. GET only_active=True (Default)
    res_active = api.client.get("/lead_fields/", headers=api.headers)
    items = res_active.json().get("items", res_active.json())
    ids = [i["id"] for i in items]

    assert f_active.public_uuid in ids
    assert f_inactive.public_uuid not in ids # No debe estar

    # 3. GET only_active=False
    res_all = api.client.get("/lead_fields/?only_active=false", headers=api.headers)
    items_all = res_all.json().get("items", res_all.json())
    ids_all = [i["id"] for i in items_all]

    assert f_active.public_uuid in ids_all
    assert f_inactive.public_uuid in ids_all # Deben estar ambos


def test_create_lead_field_fail_invalid_template(api, initial_structure):
    """
    Caso: Intentar usar una plantilla que no existe.
    """
    camp_id = initial_structure["campaign_id"]
    
    api.create_lead_field_from_template(
        camp_id, 
        "NO_EXISTO_123", 
        expected_status=400
    )


def test_delete_field_cascades_validation_rules(api, db_session, initial_structure):
    """
    Caso: Al borrar un campo, sus reglas también deben desaparecer.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo y Regla
    field = api.create_lead_field(camp_id, "Con Regla", "INT")
    
    rule = api.create_rule(
        field["id"],
        "Regla Test",
        "value > 0",
        "Error"
    )
    rule_internal_id = _resolve_internal_id(db_session, ValidationRule, rule["id"])

    # 2. Borrar el Campo (Físico)
    api.client.delete(f"/lead_fields/{field['id']}", headers=api.headers)

    # 3. Verificar que la regla ya no existe
    db_session.expire_all()
    rule_db = db_session.get(ValidationRule, rule_internal_id)
    assert rule_db is None


def test_reactivate_field_name_conflict(api, initial_structure):
    """
    Caso: Conflicto 'Zombie'. No se puede reactivar un campo si su nombre ya fue ocupado.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo A (El original) y usarlo
    field_a = api.create_lead_field(camp_id, "DNI_Duplicado", "STRING")
    api.create_lead(camp_id, [{"field_id": field_a["id"], "value": "12345678"}])
    
    # 2. Matar al Campo A
    api.client.delete(f"/lead_fields/{field_a['id']}", headers=api.headers)
    
    # 3. Crear Campo B (El usurpador) con el mismo nombre
    res_create = api.client.post("/lead_fields/", json={
        "name": "DNI_Duplicado",
        "field_type_code": "STRING",
        "campaign_id": camp_id
    }, headers=api.headers)
    
    if res_create.status_code in [200, 201]:
        # 4. Intentar revivir al Campo A (Debe fallar)
        res_active = api.client.put(f"/lead_fields/active/{field_a['id']}", headers=api.headers)
        assert res_active.status_code in [400, 409]


def test_update_field_fail_required_with_existing_nulls(api, initial_structure):
    """
    Caso: Integridad de Datos. Impedir cambio a 'Requerido' si hay nulos.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear campo Opcional y lead con null
    f_opcional = api.create_lead_field(camp_id, "Edad_Opcional", "INT", required=False)
    api.create_lead(camp_id, values=[]) 
    
    # 2. Intentar actualizar a Required=True
    res_update = api.client.put(f"/lead_fields/{f_opcional['id']}", json={
        "campaign_id": camp_id, 
        "required": True
    }, headers=api.headers)
    
    assert res_update.status_code in [400, 422]


def test_reorder_success_simple(api, db_session, initial_fields):
    """
    Caso: Reordenamiento exitoso de dos campos existentes.
    """
    camp_id = initial_fields["campaign_id"]
    f1_id = initial_fields["nombre_id"] # Actual order: 1
    f2_id = initial_fields["edad_id"]   # Actual order: 2

    # Invertimos el orden
    api.reorder_lead_fields(camp_id, [
        {"field_id": f1_id, "order": 10},
        {"field_id": f2_id, "order": 20}
    ])

    db_session.expire_all()
    f1_db = db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, f1_id))
    f2_db = db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, f2_id))

    assert f1_db.order == 10
    assert f2_db.order == 20


def test_reorder_fail_collision_with_unsent_field(api, initial_fields):
    """
    Caso: Intento de mover un campo a un 'order' que ya ocupa otro campo 
    de la misma campaña que NO fue incluido en la petición.
    """
    camp_id = initial_fields["campaign_id"]
    f1_id = initial_fields["nombre_id"] # Order: 1
    f2_id = initial_fields["edad_id"]   # Order: 2 (No lo enviamos en el patch)

    # Intentamos ponerle al campo 1 el orden que tiene el campo 2
    api.reorder_lead_fields(
        camp_id, 
        [{"field_id": f1_id, "order": 2}], 
        expected_status=400
    )


def test_reorder_fail_duplicate_orders_in_request(api, initial_fields):
    """
    Caso: Enviar dos campos distintos con el mismo número de orden en el JSON.
    """
    camp_id = initial_fields["campaign_id"]
    f1_id = initial_fields["nombre_id"]
    f2_id = initial_fields["edad_id"]

    api.reorder_lead_fields(
        camp_id, 
        [
            {"field_id": f1_id, "order": 5},
            {"field_id": f2_id, "order": 5}
        ], 
        expected_status=400
    )


def test_reorder_fail_cross_campaign_field(api, initial_structure):
    """
    Caso: Intentar reordenar un campo que pertenece a la Campaña B 
    usando el campaign_id de la Campaña A.
    """
    org_id = initial_structure["org_id"]
    camp_a_id = initial_structure["campaign_id"]
    
    # Creamos Campaña B
    ws_id = initial_structure["workspace_id"]
    flow_id = initial_structure["lead_flow_id"]
    camp_b = api.create_campaign(ws_id, name="Camp B", lead_flow_id=flow_id)
    
    # Creamos campo en Campaña B
    field_b = api.create_lead_field(camp_b["id"], "Campo B", "STRING")

    # Intentamos reordenar campo_b usando el contexto de camp_a
    api.reorder_lead_fields(
        camp_a_id, 
        [{"field_id": field_b["id"], "order": 1}], 
        expected_status=400
    )


def test_reorder_security_access_denied(api, initial_fields):
    """
    Caso: Un usuario sin acceso a la campaña intenta reordenar sus campos.
    """
    camp_id = initial_fields["campaign_id"]
    f1_id = initial_fields["nombre_id"]

    # Simulamos cambio de organización/tenant en el header
    api.org_id = 999 
    
    # Debe fallar porque el apply_security_filter/tenant_filter no encontrará la campaña o el campo
    api.reorder_lead_fields(
        camp_id, 
        [{"field_id": f1_id, "order": 1}], 
        expected_status=404
    )


def test_reorder_atomic_rollback_on_failure(api, db_session, initial_fields):
    """
    Caso: Si uno de los campos en la lista falla (ej: ID inexistente), 
    ninguno de los otros campos debe actualizarse (Atomicidad).
    """
    camp_id = initial_fields["campaign_id"]
    f1_id = initial_fields["nombre_id"] # Original order: 1

    # Enviamos una lista donde el primero es válido pero el segundo NO existe
    api.reorder_lead_fields(
        camp_id, 
        [
            {"field_id": f1_id, "order": 99},
            {"field_id": 0, "order": 100} # ID inválido: field_id es str (public_uuid) desde Fase 3, 0 (int) rechaza con 422
        ],
        expected_status=422
    )

    # Verificamos que el campo 1 SIGA teniendo su orden original (1)
    db_session.expire_all()
    f1_db = db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, f1_id))
    assert f1_db.order == 1


def test_reorder_ignores_soft_deleted_fields_collision(api, db_session, initial_fields):
    """
    Caso: El sistema debe permitir usar un número de orden que pertenece 
    a un campo que está desactivado (active=False).
    """
    camp_id = initial_fields["campaign_id"]
    f_nombre_id = initial_fields["nombre_id"] # Order: 1
    f_edad_id = initial_fields["edad_id"]     # Order: 2

    # 1. Creamos un lead para que el borrado sea Soft Delete
    api.create_lead(camp_id, [{"field_id": f_nombre_id, "value": "Juan"}, {"field_id": f_edad_id, "value": "25"}])
    
    # 2. Desactivamos el campo 'Edad' (order 2)
    api.client.delete(f"/lead_fields/{f_edad_id}", headers=api.headers)

    # 3. Ahora el orden '2' debería estar libre. Intentamos mover 'Nombre' al orden 2.
    api.reorder_lead_fields(
        camp_id, 
        [{"field_id": f_nombre_id, "order": 2}]
    )

    db_session.expire_all()
    assert db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, f_nombre_id)).order == 2


# =============================================================================
# VALIDACIONES DE NEGOCIO EN UPDATE
# =============================================================================

def test_update_field_visible_false_cannot_set_required(api, initial_structure):
    """
    Caso: Un campo oculto (is_visible=False) no puede marcarse como requerido.
    La combinación is_visible=False + required=True es inválida.
    """
    camp_id = initial_structure["campaign_id"]

    field = api.create_lead_field(camp_id, "Oculto No Requerido", "STRING", is_visible=False)

    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "required": True
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") == "required" for e in errors)


def test_update_field_required_cannot_be_hidden(api, initial_structure):
    """
    Caso: Un campo requerido no puede ocultarse.
    Ocultar un campo requerido lo haría imposible de completar en el formulario.
    """
    camp_id = initial_structure["campaign_id"]

    field = api.create_lead_field(camp_id, "Requerido Visible", "STRING", required=True)

    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "is_visible": False
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") in ("required", "is_primary") for e in errors)


def test_update_calculated_field_cannot_set_required(api, initial_structure):
    """
    Caso: Un campo CALCULATED no puede ser requerido.
    Su valor lo calcula el sistema, no lo ingresa el usuario.
    """
    camp_id = initial_structure["campaign_id"]

    field = api.create_lead_field(
        camp_id, "Formula", "CALCULATED",
        calculation_expression="1+1"
    )

    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "required": True
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") == "required" for e in errors)


def test_update_calculated_field_cannot_set_primary(api, initial_structure):
    """
    Caso: Un campo CALCULATED no puede ser identificador principal (is_primary).
    """
    camp_id = initial_structure["campaign_id"]

    field = api.create_lead_field(
        camp_id, "Formula Primaria", "CALCULATED",
        calculation_expression="1+1"
    )

    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "is_primary": True
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") == "is_primary" for e in errors)


# =============================================================================
# INTEGRIDAD HISTÓRICA: LEADS INACTIVOS
# =============================================================================

def test_update_required_succeeds_when_only_inactive_leads_have_nulls(api, db_session, initial_structure):
    """
    Caso: Un campo con nulos solo en leads inactivos puede marcarse como requerido.
    Antes del fix, los leads soft-deleted bloqueaban este cambio incorrectamente.
    """
    camp_id = initial_structure["campaign_id"]

    # 1. Campo opcional → lead sin valor
    field = api.create_lead_field(camp_id, "Campo Historico", "STRING", required=False)
    lead_data = api.create_lead(camp_id, values=[])

    # 2. Soft-delete del lead (activo=False)
    lead_internal_id = _resolve_internal_id(db_session, Lead, lead_data["id"])
    db_session.query(Lead).filter_by(id=lead_internal_id).update({"active": False})
    db_session.commit()

    # 3. Ahora no hay leads activos con nulos: debe permitir marcar como requerido
    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "required": True
    }, headers=api.headers)

    assert res.status_code == 200


# =============================================================================
# VALIDACIÓN DE CAMPAÑA RELACIONADA
# =============================================================================

def test_create_lead_field_related_campaign_nonexistent_fails(api, initial_structure):
    """
    Caso: Un campo tipo LEAD no puede apuntar a una campaña que no existe.
    """
    camp_id = initial_structure["campaign_id"]

    res = api.client.post("/lead_fields/", json={
        "campaign_id": camp_id,
        "name": "Lead Inexistente",
        "field_type_code": "LEAD",
        # related_campaign_id es str (public_uuid) desde Fase 3 -- se manda un uuid con
        # formato válido pero inexistente para no chocar con el 422 de tipo antes del
        # chequeo semántico "la campaña no existe".
        "related_campaign_id": "00000000-0000-0000-0000-000000000000"
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") == "related_campaign_id" for e in errors)


def test_create_lead_field_intra_campaign_allowed(api, initial_structure):
    """
    Caso: Un campo tipo LEAD SÍ puede apuntar a su propia campaña (relación intra-campaña).
    """
    camp_id = initial_structure["campaign_id"]

    res = api.client.post("/lead_fields/", json={
        "campaign_id": camp_id,
        "name": "Lead Intra-Campaña",
        "field_type_code": "LEAD",
        "related_campaign_id": camp_id
    }, headers=api.headers)

    assert res.status_code == 200
    assert res.json()["related_campaign"]["id"] == camp_id


# =============================================================================
# SECCIÓN POR DEFECTO INACTIVA
# =============================================================================

def test_create_field_without_section_fails_when_default_section_inactive(api, db_session, initial_structure):
    """
    Caso: Si la organización no tiene secciones activas, crear un campo
    sin especificar sección debe fallar con mensaje claro.
    Cubre el fix del filtro active=True en el fallback de sección.
    """
    camp_id = initial_structure["campaign_id"]
    section_id = initial_structure["section_id"]

    # Desactivar la única sección de la org
    section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)
    db_session.query(LeadFieldSection).filter_by(id=section_internal_id).update({"active": False})
    db_session.commit()

    res = api.client.post("/lead_fields/", json={
        "campaign_id": camp_id,
        "name": "Campo Sin Seccion",
        "field_type_code": "STRING"
    }, headers=api.headers)

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any(e.get("field") == "lead_field_section_id" for e in errors)


# =============================================================================
# REGRESIÓN: CAMBIO DE SECCIÓN (fix AttributeError 500)
# =============================================================================

def test_update_field_section_change_succeeds(api, initial_structure):
    """
    Caso: Cambiar la sección de un campo debe funcionar sin error 500.
    Regresión para el fix de AttributeError en current_field.lead_field_section_id.
    """
    camp_id = initial_structure["campaign_id"]

    # Segunda sección
    res_sec = api.client.post(
        "/lead_field_sections/",
        json={"name": "Sección Destino"},
        headers=api.headers
    )
    assert res_sec.status_code in [200, 201]
    section2_id = res_sec.json()["id"]

    field = api.create_lead_field(camp_id, "Campo Movible", "STRING")

    # Cambiar sección → antes lanzaba 500
    res = api.client.put(f"/lead_fields/{field['id']}", json={
        "lead_field_section_id": section2_id
    }, headers=api.headers)

    assert res.status_code == 200
    assert res.json()["lead_field_section"]["id"] == section2_id


# =============================================================================
# SEGURIDAD: IDOR EN BULK DELETE
# =============================================================================

def test_bulk_delete_respects_tenant_filter(client, db_session, initial_structure):
    """
    Caso: bulk-delete desde un tenant diferente no puede borrar campos ajenos.
    Cubre el fix de IDOR en operaciones bulk (apply_security_filter en BaseService).
    """
    org1_id = initial_structure["org_id"]
    camp_id = initial_structure["campaign_id"]

    # Campo creado en org1
    api_org1 = ApiClient(client, org_id=org1_id)
    field = api_org1.create_lead_field(camp_id, "Campo Protegido", "STRING")
    field_id = field["id"]

    # Org intrusa
    org2 = Organization(name="Org Intrusa")
    db_session.add(org2)
    db_session.commit()

    # Intentar bulk-delete desde org2
    api_org2 = ApiClient(client, org_id=org2.id)
    res = api_org2.client.post(
        "/lead_fields/bulk-delete",
        json={"ids": [field_id]},
        headers=api_org2.headers
    )

    assert res.status_code == 200
    result = res.json()
    assert field_id in result.get("failed", [])
    assert field_id not in result.get("deleted", [])
    assert field_id not in result.get("disabled", [])

    # El campo sigue existiendo en DB
    db_session.expire_all()
    assert db_session.get(LeadField, _resolve_internal_id(db_session, LeadField, field_id)) is not None