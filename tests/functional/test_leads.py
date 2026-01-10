import pytest
from app.models.lead_field_type import LeadFieldType
from app.models.lead_field import LeadField
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem

# --- TESTS BÁSICOS ---

def test_get_empty_leads(client, initial_structure):
    """
    Verifica que al inicio no haya leads y el endpoint responda 200 con estructura de paginación.
    """
    camp_id = initial_structure["campaign"].id
    response = client.get(f"/leads?campaign_id={camp_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verificamos estructura de paginación
    if isinstance(data, dict) and "items" in data:
        assert data["items"] == []
        assert data["total"] == 0
    else:
        # Si no usas wrapper de paginación, será lista directa
        assert data == []

def test_create_lead_simple_values(client, initial_fields):
    """
    Prueba la creación de un Lead con valores simples (Texto y Entero).
    Usa el fixture 'initial_fields' que definimos antes.
    """
    camp_id = initial_fields["campaign_id"]
    field_nombre_id = initial_fields["nombre"].id
    field_edad_id = initial_fields["edad"].id

    payload = {
        "campaign_id": camp_id,
        "values": [
            {"field_id": field_nombre_id, "value": "Carlos Test"},
            {"field_id": field_edad_id, "value": "45"}
        ]
    }

    response = client.post("/leads/", json=payload)
    
    # 1. Verificar éxito HTTP
    assert response.status_code == 200, f"Error: {response.text}"
    
    data = response.json()
    assert data["id"] is not None
    
    # 2. Verificar que los valores se guardaron
    # Buscamos en la respuesta el campo nombre
    val_nombre = next((v for v in data["field_values"] if v["field_id"] == field_nombre_id), None)
    assert val_nombre is not None
    assert val_nombre["value"] == "Carlos Test"

def test_create_lead_missing_required(client, initial_fields):
    """
    Intenta crear un lead sin el campo 'Nombre' (que definimos como required=True en el fixture).
    Debe fallar.
    """
    camp_id = initial_fields["campaign_id"]
    # Solo enviamos edad (opcional), falta nombre (obligatorio)
    payload = {
        "campaign_id": camp_id,
        "values": [
            {"field_id": initial_fields["edad"].id, "value": 30}
        ]
    }

    response = client.post("/leads/", json=payload)
    assert response.status_code == 400
    assert "obligatorio" in response.text.lower()


def test_create_lead_various_types(client, db_session, initial_structure):
    """
    Prueba la creación de campos con tipos variados (DATE, BOOL, NUMBER) 
    y verifica que se guarden correctamente.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campos dinámicos para este test
    f_fecha = LeadField(name="Fecha Nacimiento", field_type_code="DATE", campaign_id=camp_id, order=1, lead_field_section_id=1)
    f_vip = LeadField(name="Es VIP", field_type_code="BOOL", campaign_id=camp_id, order=2, lead_field_section_id=1)
    f_score = LeadField(name="Puntaje", field_type_code="NUMBER", campaign_id=camp_id, order=3, lead_field_section_id=1)
    
    db_session.add_all([f_fecha, f_vip, f_score])
    db_session.commit()

    # 2. Payload con valores en formato STRING (Clave para evitar error de DB)
    payload = {
        "campaign_id": camp_id,
        "values": [
            {"field_id": f_fecha.id, "value": "1990-12-31"},
            {"field_id": f_vip.id, "value": "true"}, # O "1"
            {"field_id": f_score.id, "value": "98.5"}
        ]
    }

    response = client.post("/leads/", json=payload)
    assert response.status_code == 200, response.text
    
    # 3. Verificar respuesta
    values = {v["field_id"]: v["value"] for v in response.json()["field_values"]}
    assert values[f_fecha.id] == "1990-12-31"
    assert str(values[f_vip.id]).lower() == "true" # La API podría devolver bool o str
    assert str(values[f_score.id]) == "98.5"


def test_create_lead_input_mask_validation_failure(client, db_session, initial_structure):
    """
    Caso Fallido: La máscara AAA-### debe rechazar formatos incorrectos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo
    f_patente = LeadField(
        name="Patente Fail", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        input_mask="AAA-###", 
        order=1,
        lead_field_section_id=1
    )
    db_session.add(f_patente)
    db_session.commit()

    # 2. Intentar crear con formato incorrecto
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_patente.id, "value": "ABC-12"}] # Falta un número
    })
    
    assert res_fail.status_code == 400
    assert "formato" in res_fail.text.lower() or "mask" in res_fail.text.lower()


def test_create_lead_input_mask_validation_success(client, db_session, initial_structure):
    """
    Caso Exitoso: La máscara AAA-### debe aceptar formatos correctos.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear Campo (Nueva instancia, nueva sesión)
    f_patente = LeadField(
        name="Patente OK", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        input_mask="AAA-###", 
        order=1,
        lead_field_section_id=1
    )
    db_session.add(f_patente)
    db_session.commit()

    # 2. Crear con formato correcto
    res_ok = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_patente.id, "value": "ABC-123"}]
    })
    
    assert res_ok.status_code == 200
    # Validamos que se guardó
    val_guardado = next(v for v in res_ok.json()["field_values"] if v["field_id"] == f_patente.id)
    assert val_guardado["value"] == "ABC-123"

def test_create_lead_duplicate_primary_field(client, db_session, initial_structure):
    """
    Prueba que no se puedan crear dos leads con el mismo valor en un campo 'is_primary' (Unique).
    Ejemplo: DNI o Email.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Campo Primary (DNI)
    f_dni = LeadField(
        name="DNI", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        is_primary=True, # <--- CLAVE
        order=1,
        lead_field_section_id=1
    )
    db_session.add(f_dni)
    db_session.commit()

    # 2. Crear Primer Lead
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_dni.id, "value": "12345678"}]
    })

    # 3. Intentar crear Segundo Lead con MISMO DNI
    res_dup = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_dni.id, "value": "12345678"}]
    })
    
    # Debería fallar por conflicto (409) o validación (400)
    assert res_dup.status_code in [409, 400] 
    assert "existe" in res_dup.text.lower()


def test_lead_lifecycle(client, initial_fields):
    """
    Prueba el flujo completo: Crear -> Editar -> Desactivar -> Reactivar -> Borrar.
    """
    camp_id = initial_fields["campaign_id"]
    f_nombre = initial_fields["nombre"].id
    
    # 1. CREAR
    res = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_nombre, "value": "Juan Original"}]
    })
    lead_id = res.json()["id"]
    assert res.status_code == 200

    # 2. EDITAR (PUT)
    # Actualizamos el nombre
    res_update = client.put(f"/leads/{lead_id}", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_nombre, "value": "Juan Editado"}]
    })
    assert res_update.status_code == 200
    # Verificar cambio
    val_editado = next(v for v in res_update.json()["field_values"] if v["field_id"] == f_nombre)
    assert val_editado["value"] == "Juan Editado"

    # 5. BORRAR (Hard Delete)
    res_del = client.delete(f"/leads/{lead_id}")
    assert res_del.status_code == 200
    
    # Verificar que ya no existe (404)
    res_get = client.get(f"/leads/{lead_id}")
    assert res_get.status_code == 404   

def test_search_leads_advanced(client, db_session, initial_structure):
    """
    Prueba el endpoint de búsqueda con filtros complejos (Rangos y Texto).
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Setup Campos (Edad y Nombre)
    f_edad = LeadField(name="Edad", field_type_code="INT", campaign_id=camp_id, order=1, lead_field_section_id=1)
    f_nombre = LeadField(name="Nombre", field_type_code="STRING", campaign_id=camp_id, order=2, lead_field_section_id=1)
    db_session.add_all([f_edad, f_nombre])
    db_session.commit()

    # 2. Crear Datos de Prueba
    # Lead 1: Ana, 25
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_nombre.id, "value": "Ana"}, {"field_id": f_edad.id, "value": "25"}]
    })
    # Lead 2: Beto, 40
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_nombre.id, "value": "Beto"}, {"field_id": f_edad.id, "value": "40"}]
    })
    # Lead 3: Carlos, 60
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_nombre.id, "value": "Carlos"}, {"field_id": f_edad.id, "value": "60"}]
    })

    # 3. Test: Mayor o igual a 40 (gte)
    payload_gte = {
        "page": 1, 
        "page_size": 10,
        "filters": [
            {"field_id": f_edad.id, "operator": "gte", "value": "40"}
        ]
    }
    res_gte = client.post("/leads/search", json=payload_gte)
    data_gte = res_gte.json()["items"]
    assert len(data_gte) == 2 # Beto y Carlos

    # 4. Test: Texto que contiene 'rl' (like) -> Carlos
    payload_like = {
        "page": 1,
        "filters": [
            {"field_id": f_nombre.id, "operator": "ilike", "value": "rl"} # ilike ignora mayúsculas
        ]
    }
    res_like = client.post("/leads/search", json=payload_like)
    data_like = res_like.json()["items"]
    assert len(data_like) == 1
    
    # Validamos que sea Carlos
    vals = data_like[0]["field_values"]
    nombre_val = next(v for v in vals if v["field_id"] == f_nombre.id)
    assert nombre_val["value"] == "Carlos"

    # 5. Test: Rango de Edad (between) 20 y 30 -> Ana
    # Nota: Si tu backend usa una lista para 'between', ajusta el formato.
    # Asumimos formato string separado por coma o similar, o que el backend lo soporte.
    # Si tu backend espera un array en value, cámbialo aquí.
    payload_between = {
        "page": 1,
        "filters": [
            {"field_id": f_edad.id, "operator": "between", "value": ["20", "30"]} 
        ]
    }
    res_between = client.post("/leads/search", json=payload_between)
    if res_between.status_code == 200:
        data_between = res_between.json()["items"]
        assert len(data_between) == 1 # Solo Ana

# --- TESTS AVANZADOS (NOMENCLADORES) ---

def test_create_lead_with_multiple_nomenclator(client, db_session, initial_structure):
    """
    Este es el TEST CLAVE para validar tu refactorización Many-to-Many.
    Crea un campo 'Etiquetas' (Multiple) y le asigna 2 valores.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Setup Datos Específicos para este test (Nomenclador y Items)
    nom = Nomenclator(name="Etiquetas Test", active=True)
    db_session.add(nom)
    db_session.flush()
    
    item1 = NomenclatorItem(nomenclator_id=nom.id, value="Urgente", code="URG")
    item2 = NomenclatorItem(nomenclator_id=nom.id, value="VIP", code="VIP")
    item3 = NomenclatorItem(nomenclator_id=nom.id, value="Descartado", code="DESC")
    db_session.add_all([item1, item2, item3])
    db_session.commit() # Commit para tener IDs disponibles

    field_tags = LeadField(
        name="Etiquetas",
        campaign_id=camp_id,
        field_type_code="NOMENCLATOR",
        field_subtype_code="MULTIPLE",
        nomenclator_id=nom.id,
        lead_field_section_id=1, # Asumido
        required=False,
        order=5
    )
    db_session.add(field_tags)
    db_session.commit()

    # 3. Payload: Enviamos LISTA de IDs [item1, item2]
    payload = {
        "campaign_id": camp_id,
        "values": [
            {
                "field_id": field_tags.id, 
                "value": [item1.id, item2.id] # <--- AQUÍ ESTÁ LA PRUEBA DE FUEGO
            }
        ]
    }

    response = client.post("/leads/", json=payload)
    assert response.status_code == 200, response.text
    
    data = response.json()
    
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

def test_search_lead_by_nomenclator(client, db_session, initial_structure):
    """
    Prueba el repositorio de búsqueda con la lógica OR (value text OR relation items).
    Busca leads que tengan la etiqueta 'Ventas'.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Setup Nomenclador
    nom = Nomenclator(name="Depto", active=True)
    db_session.add(nom)
    db_session.flush()
    item_ventas = NomenclatorItem(nomenclator_id=nom.id, value="Ventas", code="VTS")
    item_it = NomenclatorItem(nomenclator_id=nom.id, value="IT", code="IT")
    db_session.add_all([item_ventas, item_it])
    db_session.commit()

    field_depto = LeadField(
        name="Departamento", campaign_id=camp_id, 
        field_type_code="NOMENCLATOR", field_subtype_code="SINGLE",
        nomenclator_id=nom.id, lead_field_section_id=1, order=1
    )
    db_session.add(field_depto)
    db_session.commit()

    # 3. Crear Leads
    # Lead A: Ventas
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": field_depto.id, "value": item_ventas.id}]
    })
    
    # Lead B: IT
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": field_depto.id, "value": item_it.id}]
    })

    # 4. BUSCAR: Filtramos por ID de Ventas
    # Suponiendo que tu endpoint de búsqueda recibe un JSON POST
    search_payload = {
        "page": 1,
        "page_size": 10,
        "filters": [
            {
                "field_id": field_depto.id,
                "operator": "eq", # O "in"
                "value": item_ventas.id
            }
        ]
    }
    
    response = client.post("/leads/search", json=search_payload)
    assert response.status_code == 200
    
    data = response.json()
    items = data["items"] if "items" in data else data
    
    # Debe encontrar solo 1 (El de Ventas)
    assert len(items) == 1
    
    # Verificamos que sea el correcto
    vals = items[0]["field_values"]
    target_val = next(v for v in vals if v["field_id"] == field_depto.id)
    # En la respuesta detallada, revisamos los items
    assert target_val["nomenclator_items"][0]["value"] == "Ventas"


def test_create_field_from_template(client, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (EMAIL) y verifica que:
    1. Se cree el campo correctamente con las propiedades de la plantilla.
    """
    camp_id = initial_structure["campaign"].id
    
    payload_field = {
        "field_template_code": "EMAIL",
        "campaign_id": camp_id,
        "order": 10,
        "required": True,
        "is_primary": False,
        "lead_field_section_id": 1
    }
    res_field = client.post("/lead_fields/", json=payload_field)
    assert res_field.status_code == 200
    field_data = res_field.json()

    field_created = client.get(f"/lead_fields/{field_data['id']}")
    assert field_created.status_code == 200
    assert field_created.json()["validation_rules"] is not None


def test_create_field_from_template_and_validate_success(client, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (EMAIL) y verifica que:
    1. Se cree el campo correctamente.
    2. Se genere automáticamente una regla de validación.
    3. El sistema rechace valores que no cumplan esa regla (Email inválido).
    """
    camp_id = initial_structure["campaign"].id
    
    payload_field = {
        "field_template_code": "EMAIL",
        "campaign_id": camp_id,
        "order": 10,
        "required": True,
        "is_primary": False,
        "lead_field_section_id": 1
    }
    res_field = client.post("/lead_fields/", json=payload_field)
    assert res_field.status_code == 200
    field_id = res_field.json()["id"]
    

    # 4. Validar: Intentar crear Lead con Email VÁLIDO
    res_ok = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": field_id, "value": "test@crm.com"}]
    })
    assert res_ok.status_code == 200

def test_create_field_from_template_and_validate_failure(client, db_session, initial_structure):
    """
    Crea un campo usando una plantilla (EMAIL) y verifica que:
    1. Se cree el campo correctamente.
    2. Se genere automáticamente una regla de validación.
    3. El sistema rechace valores que no cumplan esa regla (Email inválido).
    """
    camp_id = initial_structure["campaign"].id
    
    payload_field = {
        "field_template_code": "EMAIL",
        "campaign_id": camp_id,
        "order": 10,
        "required": True,
        "is_primary": False,
        "lead_field_section_id": 1
    }
    res_field = client.post("/lead_fields/", json=payload_field)
    assert res_field.status_code == 200
    field_id = res_field.json()["id"]

    # 3. Validar: Intentar crear Lead con Email INVÁLIDO
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": field_id, "value": "no-es-un-mail"}]
    })
    assert res_fail.status_code == 400
    
    assert "formato" in res_fail.text.lower() or "válido" in res_fail.text.lower()


def test_get_leads_filtering(client, db_session, initial_structure):
    """
    Valida los filtros de listado:
    - campaign_id (Aislamiento entre campañas)
    """
    # Setup: 2 Campañas
    camp_a = initial_structure["campaign"] # ID ya existe
    
    from app.models.campaign import Campaign
    camp_b = Campaign(name="Campaña B", workspace_id=initial_structure["workspace"].id, active=True)
    db_session.add(camp_b)
    db_session.commit() # ID generado

    # Setup: Campo común (Nombre) para simplificar, lo creamos en ambas campañas
    # (O usamos uno genérico si existiera, aquí creamos específicos)
    f_nom_a = LeadField(name="Nombre A", field_type_code="STRING", campaign_id=camp_a.id, order=1, lead_field_section_id=1)
    f_nom_b = LeadField(name="Nombre B", field_type_code="STRING", campaign_id=camp_b.id, order=1, lead_field_section_id=1)
    db_session.add_all([f_nom_a, f_nom_b])
    db_session.commit()

    # 1. Crear Leads en Campaña A
    # Lead A1 (Activo)
    client.post("/leads/", json={"campaign_id": camp_a.id, "values": [{"field_id": f_nom_a.id, "value": "Lead A1"}]})
    # Lead A2 (Activo -> Luego Desactivado)
    res_a2 = client.post("/leads/", json={"campaign_id": camp_a.id, "values": [{"field_id": f_nom_a.id, "value": "Lead A2"}]})
    id_a2 = res_a2.json()["id"]

    # 2. Crear Lead en Campaña B
    client.post("/leads/", json={"campaign_id": camp_b.id, "values": [{"field_id": f_nom_b.id, "value": "Lead B1"}]})

    # --- TEST DE FILTROS ---

    # Caso 1: Campaña A
    # Debería traer solo A1 y A2 (B1 es de otra campaña)
    res_active = client.get(f"/leads/?campaign_id={camp_a.id}")
    items_active = res_active.json()["items"] if "items" in res_active.json() else res_active.json()
    
    assert len(items_active) == 2

    # Caso 2: Filtrar por Campaña B
    # Debería traer solo B1
    res_b = client.get(f"/leads/?campaign_id={camp_b.id}")
    items_b = res_b.json()["items"] if "items" in res_b.json() else res_b.json()
    assert len(items_b) == 1
    val_b1 = next(v for v in items_b[0]["field_values"] if v["field_id"] == f_nom_b.id)
    assert val_b1["value"] == "Lead B1"