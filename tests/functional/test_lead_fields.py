import pytest
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule

def test_lead_field_lifecycle_no_data(api, db_session, initial_structure):
    """
    Caso: Crear un campo y borrarlo CUANDO NO HAY LEADS.
    Resultado esperado: Borrado físico inmediato (Action: deleted).
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear Campo vía API
    field = api.create_lead_field(camp_id, "Campo Efímero", "STRING")
    field_id = field["id"]

    # 2. Borrar Campo (Usamos client directo para validar la respuesta específica 'action')
    res_del = api.client.delete(f"/lead_fields/{field_id}", headers=api.headers)
    
    assert res_del.status_code == 200
    assert res_del.json()["action"] == "deleted"
    
    # 3. Verificar en DB que no existe (Borrado Físico)
    db_session.expire_all()
    field_db = db_session.get(LeadField, field_id)
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
    new_val = next((v for v in lead_values if v["field_id"] == f_new["id"]), None)
    
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
    
    api.create_lead(camp_id, [{"field_id": f_dato["id"], "value": 100}])

    # 2. Intentar Borrar el Campo
    res_del = api.client.delete(f"/lead_fields/{f_dato['id']}", headers=api.headers)
    
    # 3. Validar respuesta Híbrida
    assert res_del.status_code == 200
    data = res_del.json()
    assert data["action"] == "disabled" # <--- CLAVE: No borró, solo desactivó

    # 4. Verificar en DB (Soft Delete)
    db_session.expire_all()
    field_db = db_session.get(LeadField, f_dato["id"])
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
    f_db = db_session.get(LeadField, f_test["id"])
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
    val_guardado = next((v for v in data["field_values"] if v["field_id"] == f_opcional["id"]), None)
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
        "campaign_id": camp_id,
        "lead_field_section_id": 1
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
        "lead_field_section_id": 1,
        "required": True # <--- Conflicto
    }, headers=api.headers)
    
    assert res.status_code == 400


def test_get_fields_filtering_active(api, db_session, initial_structure):
    """
    Caso: Verificar que el listado oculte los campos desactivados (Soft Deleted)
    por defecto.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]

    # 1. Crear Campo A (Activo) y B (Inactivo)
    f_active = LeadField(name="Visible", field_type_code="STRING", campaign_id=camp_id, active=True, order=1, lead_field_section_id=1, organization_id=org_id)
    f_inactive = LeadField(name="Oculto", field_type_code="STRING", campaign_id=camp_id, active=False, order=2, lead_field_section_id=1, organization_id=org_id)
    db_session.add_all([f_active, f_inactive])
    db_session.commit()

    # 2. GET only_active=True (Default)
    res_active = api.client.get("/lead_fields/", headers=api.headers)
    items = res_active.json().get("items", res_active.json())
    ids = [i["id"] for i in items]

    assert f_active.id in ids
    assert f_inactive.id not in ids # No debe estar

    # 3. GET only_active=False
    res_all = api.client.get("/lead_fields/?only_active=false", headers=api.headers)
    items_all = res_all.json().get("items", res_all.json())
    ids_all = [i["id"] for i in items_all]

    assert f_active.id in ids_all
    assert f_inactive.id in ids_all # Deben estar ambos


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
    
    # 2. Borrar el Campo (Físico)
    api.client.delete(f"/lead_fields/{field['id']}", headers=api.headers)

    # 3. Verificar que la regla ya no existe
    db_session.expire_all()
    rule_db = db_session.get(ValidationRule, rule["id"])
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
        "campaign_id": camp_id,
        "lead_field_section_id": 1,
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
        "lead_field_section_id": 1,
        "required": True
    }, headers=api.headers)
    
    assert res_update.status_code in [400, 422]