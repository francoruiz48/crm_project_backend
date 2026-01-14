import pytest
from app.models.lead_field import LeadField
from app.models.lead_field_value import LeadFieldValue

def test_lead_field_lifecycle_no_data(client, db_session, initial_structure):
    """
    Caso: Crear un campo y borrarlo CUANDO NO HAY LEADS.
    Resultado esperado: Borrado físico inmediato (Action: deleted).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo
    payload = {
        "name": "Campo Efímero",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "order": 1,
        "required": False,
        "lead_field_section_id": 1
    }
    res_create = client.post("/lead_fields/", json=payload)
    assert res_create.status_code == 200
    field_id = res_create.json()["id"]

    # 2. Borrar Campo (Sin leads en la campaña)
    res_del = client.delete(f"/lead_fields/{field_id}")
    
    assert res_del.status_code == 200
    assert res_del.json()["action"] == "deleted"
    
    # 3. Verificar en DB que no existe
    # Limpiamos la sesión para asegurar lectura fresca
    db_session.expire_all()
    field_db = db_session.get(LeadField, field_id)
    assert field_db is None


def test_lead_field_backfill_existing_leads(client, db_session, initial_structure):
    """
    Caso: Backfill (Relleno automático).
    1. Crear Leads primero.
    2. Crear un NUEVO campo después.
    3. Verificar que los leads viejos tengan ese campo (con valor None o Default).
    """
    camp_id = initial_structure["campaign"].id
    
    # Setup: Crear campo base y un Lead
    f_base = LeadField(name="Base", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_base)
    db_session.commit()

    # Crear Lead
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_base.id, "value": "Lead Viejo"}]
    })

    # --- TEST: Agregar nuevo campo con Default Value ---
    payload_new_field = {
        "name": "Nuevo Campo Backfill",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "order": 2,
        "default_value": "Relleno Automático", # <--- Probamos que use el default
        "required": False, # Obligatorio false porque ya hay datos
        "lead_field_section_id": 1
    }
    
    res_field = client.post("/lead_fields/", json=payload_new_field)
    assert res_field.status_code == 200
    new_field_id = res_field.json()["id"]

    # --- VERIFICACIÓN ---
    # Obtenemos el Lead para ver si tiene el valor nuevo
    res_leads = client.get(f"/leads?campaign_id={camp_id}")
    leads = res_leads.json()["items"]
    
    assert len(leads) == 1
    lead_values = leads[0]["field_values"]
    
    # Buscamos el valor del nuevo campo
    new_val = next((v for v in lead_values if v["field_id"] == new_field_id), None)
    
    assert new_val is not None
    assert new_val["value"] == "Relleno Automático" # Debe haberse rellenado solo


def test_lead_field_delete_with_data_soft_delete(client, db_session, initial_structure):
    """
    Caso: Borrar un campo CUANDO YA TIENE DATOS (Leads usándolo).
    Resultado esperado: Desactivación (Soft Delete) para proteger integridad histórica.
    Action: disabled.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo y Lead que lo usa
    f_dato = LeadField(name="Dato Importante", field_type_code="INT", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_dato)
    db_session.commit()

    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_dato.id, "value": "100"}]
    })

    # 2. Intentar Borrar el Campo
    res_del = client.delete(f"/lead_fields/{f_dato.id}")
    
    # 3. Validar respuesta Híbrida
    assert res_del.status_code == 200
    data = res_del.json()
    assert data["action"] == "disabled" # <--- CLAVE: No borró, solo desactivó

    # 4. Verificar en DB (Soft Delete)
    db_session.expire_all()
    field_db = db_session.get(LeadField, f_dato.id)
    assert field_db is not None
    assert field_db.active is False # Está inactivo


def test_create_lead_ignores_disabled_required_field(client, db_session, initial_structure):
    """
    Caso: Campo Requerido que fue Desactivado (Soft Delete).
    Prueba: Al crear un nuevo Lead, el sistema debe IGNORAR la obligatoriedad de ese campo
    porque está inactivo.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo Requerido
    f_req = LeadField(name="Campo Obligatorio", field_type_code="STRING", campaign_id=camp_id, required=True, order=1, lead_field_section_id=1)
    db_session.add(f_req)
    db_session.commit()

    f_no_req = LeadField(name="Campo No Obligatorio", field_type_code="STRING", campaign_id=camp_id, required=False, order=2, lead_field_section_id=1)
    db_session.add(f_no_req)
    db_session.commit()

    # (Truco para simular Soft Delete con dependencias)
    # Creamos un lead primero para "trabar" el borrado físico
    client.post("/leads/", json={"campaign_id": camp_id, "values": [{"field_id": f_req.id, "value": "Valor 1"}]})
    
    # Borramos -> Se transforma en Soft Delete (disabled)
    client.delete(f"/lead_fields/{f_req.id}")

    # 2. Intentar crear Lead 2 SIN enviar el campo requerido (que ahora está off)
    payload_lead_2 = {
        "campaign_id": camp_id,
        "values": [] # No mandamos nada
    }
    
    res_lead = client.post("/leads/", json=payload_lead_2)
    
    # DEBERÍA FUNCIONAR (200 OK) porque el campo inactivo no se valida
    assert res_lead.status_code == 200, f"Falló la creación: {res_lead.text}"


def test_cannot_add_required_field_to_campaign_with_leads(client, db_session, initial_structure):
    """
    Caso: Integridad de datos.
    No se debe permitir crear un campo REQUIRED si la campaña ya tiene leads,
    porque los leads viejos quedarían inválidos (valor nulo en campo required).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Lead en la campaña (Campana sucia)
    f_existente = LeadField(name="A", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_existente)
    db_session.commit()
    
    client.post("/leads/", json={"campaign_id": camp_id, "values": [{"field_id": f_existente.id, "value": "x"}]})

    # 2. Intentar agregar nuevo campo Required
    payload = {
        "name": "Campo Imposible",
        "field_type_code": "INT",
        "campaign_id": camp_id,
        "required": True, # <--- ESTO ES LO ILEGAL
        "order": 2,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    
    assert res.status_code == 400
    assert "no se puede crear" in res.text.lower() and "required" in res.text.lower()


def test_reactivate_field(client, db_session, initial_structure):
    """
    Caso: Reactivar un campo previamente eliminado (Soft Deleted).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Setup: Campo con datos -> Soft Delete
    f_test = LeadField(name="Zombie Field", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_test)
    db_session.commit()

    f_test_2 = LeadField(name="Zombie Field 2", field_type_code="STRING", campaign_id=camp_id, order=2, lead_field_section_id=1)
    db_session.add(f_test_2)
    db_session.commit()
    
    response = client.post("/leads/", json={"campaign_id": camp_id, "values": [{"field_id": f_test.id, "value": "A"}]})
    assert response.status_code == 200
    response = client.delete(f"/lead_fields/{f_test.id}")
    assert response.status_code == 200

    # 2. Reactivar
    res_active = client.put(f"/lead_fields/active/{f_test.id}")
    assert res_active.status_code == 200, f"Error: {response.text}"
    
    # 3. Validar
    db_session.expire_all()
    f_db = db_session.get(LeadField, f_test.id)
    assert f_db.active is True


def test_create_lead_fails_no_fields_defined(client, initial_structure):
    """
    Caso: Campaña nueva sin NINGÚN campo creado.
    Resultado: 400 Bad Request (No se puede crear lead sin estructura).
    """
    camp_id = initial_structure["campaign"].id
    
    # Intentamos crear lead enviando lista vacía (o con basura, da igual)
    payload = {
        "campaign_id": camp_id,
        "values": []
    }
    
    response = client.post("/leads/", json=payload)
    
    assert response.status_code == 400
    assert "no tiene campos activos" in response.text.lower()


def test_create_lead_fails_all_fields_disabled(client, db_session, initial_structure):
    """
    Caso: Campaña tenía campos, pero fueron TODOS desactivados (Soft Delete).
    Resultado: 400 Bad Request (Estructuralmente está vacía para el usuario).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear un campo
    f_temp = LeadField(name="Campo X", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_temp)
    db_session.commit()
    
    # 2. Desactivarlo (Borrado lógico)
    client.delete(f"/lead_fields/{f_temp.id}")
    
    # 3. Intentar crear lead
    payload = {
        "campaign_id": camp_id,
        "values": [] 
    }
    response = client.post("/leads/", json=payload)
    
    assert response.status_code == 400
    assert "no tiene campos activos" in response.text.lower()


def test_create_lead_success_empty_values_optional_fields(client, db_session, initial_structure):
    """
    Caso: Campaña tiene campos ACTIVOS, pero NO SON OBLIGATORIOS.
    Enviamos values=[], el sistema debe rellenar con None/Default.
    Resultado: 200 OK.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo Opcional
    f_opcional = LeadField(
        name="Comentarios", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        required=False, # <--- CLAVE
        order=1,
        lead_field_section_id=1
    )
    db_session.add(f_opcional)
    db_session.commit()
    
    # 2. Crear Lead sin enviar valores
    payload = {
        "campaign_id": camp_id,
        "values": [] 
    }
    response = client.post("/leads/", json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    # Verificamos que se creó el valor nulo internamente
    val_guardado = next((v for v in data["field_values"] if v["field_id"] == f_opcional.id), None)
    assert val_guardado is not None
    assert val_guardado["value"] is None

def test_create_field_fail_order_collision(client, db_session, initial_structure):
    """
    Caso: Intentar crear un campo con un 'order' manual que ya está ocupado.
    Resultado: 400 Bad Request.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo A en orden 5
    client.post("/lead_fields/", json={
        "name": "Campo A",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "order": 5,
        "lead_field_section_id": 1
    })

    # 2. Intentar Crear Campo B en orden 5
    res = client.post("/lead_fields/", json={
        "name": "Campo B",
        "field_type_code": "INT",
        "campaign_id": camp_id,
        "order": 5, # ¡Conflicto!
        "lead_field_section_id": 1
    })
    
    assert res.status_code == 400
    assert "orden" in res.text.lower() and "ocupado" in res.text.lower()


def test_create_field_fail_nomenclator_type_mismatch(client, db_session, initial_structure):
    """
    Caso: Enviar 'nomenclator_id' pero con un 'field_type_code' que no es SELECTOR ni CHECKBOX.
    Resultado: 400 Bad Request (Incoherencia de datos).
    """
    camp_id = initial_structure["campaign"].id
    
    # Necesitamos un nomenclador real para el test
    from app.models.nomenclator import Nomenclator
    nom = Nomenclator(name="Paises Test", active=True)
    db_session.add(nom)
    db_session.commit()

    payload = {
        "name": "Pais",
        "campaign_id": camp_id,
        "nomenclator_id": nom.id,
        "field_type_code": "INT", # <--- ERROR: Debería ser SELECTOR o nulo
        "order": 1,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    assert res.status_code == 400
    # Validamos que el mensaje mencione la discrepancia
    assert "nomenclator_id" in res.text.lower()


def test_create_field_fail_subtype_mismatch(client, initial_structure):
    """
    Caso: Enviar un subtipo que no pertenece al tipo de campo padre.
    Ejemplo: Tipo FILE con subtipo SIMPLE.
    """
    camp_id = initial_structure["campaign"].id
    
    payload = {
        "name": "Archivo Loco",
        "campaign_id": camp_id,
        "field_type_code": "FILE",
        "field_subtype_code": "SELECTOR_SIMPLE", # <--- ERROR: Esto es de selectores
        "order": 1,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    assert res.status_code == 400
    assert "no es válido" in res.text.lower()


def test_create_field_fail_missing_subtype(client, initial_structure):
    """
    Caso: Crear un campo que REQUIERE subtipo (como SELECTOR) sin enviarlo.
    """
    camp_id = initial_structure["campaign"].id
    
    payload = {
        "name": "Selector Incompleto",
        "campaign_id": camp_id,
        "field_type_code": "SELECTOR",
        # Falta field_subtype_code
        "order": 1,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    assert res.status_code == 400
    assert "requiere especificar un subtipo" in res.text.lower()


def test_create_field_fail_primary_with_existing_leads(client, db_session, initial_structure):
    """
    Caso: Intentar agregar un campo 'is_primary' (identificador único) cuando ya existen leads.
    Esto debe fallar porque no podemos garantizar que los leads viejos sean únicos retrospectivamente.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear un campo base y un lead (para ensuciar la campaña)
    f_base = LeadField(name="Base", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_base)
    db_session.commit()
    
    client.post("/leads/", json={"campaign_id": camp_id, "values": [{"field_id": f_base.id, "value": "test"}]})

    # 2. Intentar crear campo Primary
    payload = {
        "name": "DNI Nuevo",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "is_primary": True, # <--- PROHIBIDO con datos existentes
        "order": 2,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    assert res.status_code == 400
    assert "primary" in res.text.lower() and "leads" in res.text.lower()


def test_update_field_fail_change_type(client, initial_structure):
    """
    Caso: Intentar cambiar el tipo de dato de un campo existente.
    Esto suele prohibirse para evitar corromper datos antiguos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campo STRING
    res = client.post("/lead_fields/", json={
        "name": "Original",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "order": 1,
        "lead_field_section_id": 1
    })
    field_id = res.json()["id"]

    # 2. Intentar cambiarlo a INT
    res_update = client.put(f"/lead_fields/{field_id}", json={
        "field_type_code": "INT",
        "campaign_id": camp_id,
        "order": 1,
        "lead_field_section_id": 1
    })
    
    # Dependiendo de tu implementación, esto debería fallar o ser ignorado.
    # Asumiendo que es estricto:
    if res_update.status_code == 200:
        # Si la API lo permite, verificar que NO haya cambiado
        assert res_update.json()["field_type_code"] == "STRING"
    else:
        assert res_update.status_code == 400


def test_update_field_fail_required_with_null_values(client, db_session, initial_structure):
    """
    Caso: Hacer REQUERIDO un campo que ya tiene valores NULOS en la BD.
    Debe fallar por integridad de datos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo Opcional y un Lead sin valor (Null)
    f_opcional = LeadField(name="Opcional", field_type_code="STRING", campaign_id=camp_id, required=False, order=1, lead_field_section_id=1)
    db_session.add(f_opcional)
    db_session.commit()
    
    client.post("/leads/", json={"campaign_id": camp_id, "values": []}) # Lead con valor null en f_opcional

    # 2. Intentar actualizar a Required=True
    res = client.put(f"/lead_fields/{f_opcional.id}", json={
        "campaign_id": camp_id,
        "order": 1,
        "lead_field_section_id": 1,
        "required": True # <--- Conflicto con el lead existente
    })
    
    assert res.status_code == 400
    assert "requerido" in res.text.lower()


def test_get_fields_filtering_active(client, db_session, initial_structure):
    """
    Caso: Verificar que el listado oculte los campos desactivados (Soft Deleted)
    por defecto.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo A (Activo) y B (Inactivo)
    f_active = LeadField(name="Visible", field_type_code="STRING", campaign_id=camp_id, active=True, order=1, lead_field_section_id=1)
    f_inactive = LeadField(name="Oculto", field_type_code="STRING", campaign_id=camp_id, active=False, order=2, lead_field_section_id=1) # Simulamos soft delete
    db_session.add_all([f_active, f_inactive])
    db_session.commit()

    # 2. GET only_active=True (Default)
    res_active = client.get("/lead_fields/")
    items = res_active.json()["items"] if "items" in res_active.json() else res_active.json()
    ids = [i["id"] for i in items]
    
    assert f_active.id in ids
    assert f_inactive.id not in ids # No debe estar

    # 3. GET only_active=False
    res_all = client.get("/lead_fields/?only_active=false")
    items_all = res_all.json()["items"] if "items" in res_all.json() else res_all.json()
    ids_all = [i["id"] for i in items_all]
    
    assert f_active.id in ids_all
    assert f_inactive.id in ids_all # Deben estar ambos


def test_create_field_fail_invalid_template(client, initial_structure):
    """
    Caso: Intentar usar una plantilla que no existe en el sistema.
    """
    camp_id = initial_structure["campaign"].id
    
    payload = {
        "field_template_code": "NO_EXISTO_123",
        "campaign_id": camp_id,
        "order": 1,
        "lead_field_section_id": 1
    }
    
    res = client.post("/lead_fields/", json=payload)
    assert res.status_code == 400
    assert "plantilla" in res.text.lower()


def test_delete_field_cascades_validation_rules(client, db_session, initial_structure):
    """
    Caso: Al borrar un campo, verificar que sus reglas de validación también 
    se borren (o desactiven) para no dejar huérfanos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo y Regla
    f_con_regla = LeadField(name="Con Regla", field_type_code="INT", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_con_regla)
    db_session.commit()
    
    # Crear regla manualmente (o via servicio)
    from app.models.validation_rule import ValidationRule
    rule = ValidationRule(field_id=f_con_regla.id, name="Regla Test", expression="value > 0", error_message="Error")
    db_session.add(rule)
    db_session.commit()
    
    rule_id = rule.id

    # 2. Borrar el Campo (Físico porque no tiene leads)
    res_del = client.delete(f"/lead_fields/{f_con_regla.id}")
    assert res_del.status_code == 200

    # 3. Verificar que la regla ya no existe (o está inactiva si fue soft delete)
    # Como fue delete físico del campo, la regla debería haberse ido por CASCADE de la BD 
    # o por lógica del servicio.
    db_session.expire_all()
    rule_db = db_session.get(ValidationRule, rule_id)
    
    # Si tienes 'on delete cascade' en la DB, esto será None.
    # Si tienes soft delete logic en el servicio, podría ser None o active=False.
    assert rule_db is None


def test_reactivate_field_name_conflict(client, db_session, initial_structure):
    """
    Caso 1: Conflicto 'Zombie'.
    Verifica que no se pueda reactivar un campo si su nombre ya fue ocupado
    por otro campo activo mientras el primero estaba 'muerto' (soft deleted).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo A (El original)
    field_a = LeadField(name="DNI_Duplicado", field_type_code="STRING", campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(field_a)
    db_session.commit()

    client.post("/leads/", json={"campaign_id": camp_id, "values": [{"field_id": field_a.id, "value": "12345678"}]})
    
    # 2. Matar al Campo A (Soft Delete)
    client.delete(f"/lead_fields/{field_a.id}")
    
    # 3. Crear Campo B (El usurpador) con el mismo nombre
    res_create = client.post("/lead_fields/", json={
        "name": "DNI_Duplicado",
        "field_type_code": "STRING",
        "campaign_id": camp_id,
        "order": 2,
        "lead_field_section_id": 1
    })
    
    # Si tu sistema permite crear duplicados si el anterior está borrado, esto pasará (201/200).
    # Si tu sistema es muy estricto, fallará aquí (400/409). Ajusta según tu lógica.
    if res_create.status_code in [200, 201]:
        # 4. Intentar revivir al Campo A
        # Aquí es donde DEBE fallar, porque ya existe uno activo con ese nombre.
        res_active = client.put(f"/lead_fields/active/{field_a.id}")
        
        assert res_active.status_code in [400, 409]
        assert "ya existe" in res_active.text.lower() or "conflict" in res_active.text.lower()



def test_update_field_fail_required_with_existing_nulls(client, db_session, initial_structure):
    """
    Caso 2 (Opción A): Integridad de Datos.
    No se debe permitir cambiar un campo a 'Requerido' si ya existen Leads
    que tienen ese valor vacío (NULL) en la base de datos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campo Opcional
    f_opcional = LeadField(name="Edad_Opcional", field_type_code="INT", required=False, campaign_id=camp_id, order=1, lead_field_section_id=1)
    db_session.add(f_opcional)
    db_session.commit()
    
    # 2. Crear un Lead SIN enviar ese campo (valor será NULL en BD)
    res_lead = client.post("/leads/", json={
        "campaign_id": camp_id, 
        "values": [] # Lista vacía, el campo opcional queda null
    })
    assert res_lead.status_code == 200
    
    # 3. Intentar actualizar el campo a Required=True
    res_update = client.put(f"/lead_fields/{f_opcional.id}", json={"field_type_code": "INT", "required": True, "campaign_id": camp_id, "order": 1, "lead_field_section_id": 1})
    
    # 4. Verificaciones
    assert res_update.status_code in [400, 422], \
        "El sistema debió impedir el cambio a requerido porque hay leads con valores nulos."
        
    error_msg = res_update.json().get("detail", "").lower()
    assert "null" in error_msg or "exist" in error_msg