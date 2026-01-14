import pytest

def test_calculated_field_arithmetic(client, initial_structure):
    """
    Prueba aritmética simple: Total = Precio * Cantidad
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campos base
    f_precio = client.post("/lead_fields/", json={
        "name": "Precio", "field_type_code": "NUMBER", "campaign_id": camp_id, "order": 1, "lead_field_section_id": 1
    }).json()
    
    f_cantidad = client.post("/lead_fields/", json={
        "name": "Cantidad", "field_type_code": "INT", "campaign_id": camp_id, "order": 2, "lead_field_section_id": 1
    }).json()

    # 2. Crear campo calculado
    f_total = client.post("/lead_fields/", json={
        "name": "Total", 
        "field_type_code": "CALCULATED", 
        "campaign_id": camp_id, 
        "order": 3, 
        "lead_field_section_id": 1,
        # Fórmula Excel
        "calculation_expression": "Precio * Cantidad"
    }).json()

    # 3. Crear Lead
    payload = {
        "campaign_id": camp_id,
        "values": [
            {"field_id": f_precio["id"], "value": 10.5},
            {"field_id": f_cantidad["id"], "value": 4}
        ]
    }
    res = client.post("/leads/", json=payload)
    assert res.status_code == 200
    
    # 4. Verificar cálculo (10.5 * 4 = 42.0)
    values = res.json()["field_values"]
    val_total = next(v for v in values if v["field_id"] == f_total["id"])
    assert float(val_total["value"]) == 42.0

def test_calculated_field_logic_and_text(client, initial_structure):
    """
    Prueba lógica compleja: IF + Concatenación
    Fórmula: IF(Edad >= 18, "Mayor: " & Nombre, "Menor")
    """
    camp_id = initial_structure["campaign"].id
    
    f_nombre = client.post("/lead_fields/", json={"name": "Nombre", "field_type_code": "STRING", "campaign_id": camp_id, "order": 1, "lead_field_section_id": 1}).json()
    f_edad = client.post("/lead_fields/", json={"name": "Edad", "field_type_code": "INT", "campaign_id": camp_id, "order": 2, "lead_field_section_id": 1}).json()

    f_estado = client.post("/lead_fields/", json={
        "name": "Estado", "field_type_code": "CALCULATED", "campaign_id": camp_id, "order": 3, "lead_field_section_id": 1,
        # Fórmula con IF y Concatenación (&)
        "calculation_expression": 'IF(Edad >= 18, "Mayor: " & Nombre, "Menor")'
    }).json()

    # Caso 1: Mayor
    res1 = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [
            {"field_id": f_nombre["id"], "value": "Juan"},
            {"field_id": f_edad["id"], "value": 20}
        ]
    })
    val1 = next(v for v in res1.json()["field_values"] if v["field_id"] == f_estado["id"])
    assert val1["value"] == "Mayor: Juan"

    # Caso 2: Menor
    res2 = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [
            {"field_id": f_nombre["id"], "value": "Pedrito"},
            {"field_id": f_edad["id"], "value": 10}
        ]
    })
    val2 = next(v for v in res2.json()["field_values"] if v["field_id"] == f_estado["id"])
    assert val2["value"] == "Menor"

def test_calculated_field_cleaning_functions(client, initial_structure):
    """
    Prueba las funciones de limpieza: TRIM, UPPER, PROPER
    """
    camp_id = initial_structure["campaign"].id
    
    f_sucio = client.post("/lead_fields/", json={"name": "InputSucio", "field_type_code": "STRING", "campaign_id": camp_id, "order": 1, "lead_field_section_id": 1}).json()

    # Campo que limpia: PROPER(TRIM(InputSucio))
    # Ej: "  juan PEREZ  " -> "Juan Perez"
    f_limpio = client.post("/lead_fields/", json={
        "name": "InputLimpio", "field_type_code": "CALCULATED", "campaign_id": camp_id, "order": 2, "lead_field_section_id": 1,
        "calculation_expression": 'PROPER(TRIM(InputSucio))'
    }).json()

    res = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [
            {"field_id": f_sucio["id"], "value": "  juan PEREZ  "}
        ]
    })
    
    val_limpio = next(v for v in res.json()["field_values"] if v["field_id"] == f_limpio["id"])
    assert val_limpio["value"] == "Juan Perez"