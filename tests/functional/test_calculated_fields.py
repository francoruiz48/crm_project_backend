import pytest

def test_calculated_field_intent_to_assign_a_value(api, initial_structure):
    """
    Intento asignar valor al campo que se define como CALCULATED.
    El sistema debe ignorar el valor enviado y calcular el correcto.
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campos base
    f_precio = api.create_lead_field(camp_id, "Precio", "NUMBER")
    f_cantidad = api.create_lead_field(camp_id, "Cantidad", "INT")

    # 2. Crear campo calculado
    f_total = api.create_lead_field(
        camp_id, 
        "Total", 
        "CALCULATED", 
        calculation_expression="Precio * Cantidad"
    )

    # 3. Crear Lead con valor "trucho" en el campo calculado
    lead_resp = api.create_lead(camp_id, [
        {"field_id": f_precio["id"], "value": 5},
        {"field_id": f_cantidad["id"], "value": 4},
        {"field_id": f_total["id"], "value": 1}  # <--- Intento de override (debe ser ignorado)
    ])
    
    # 4. Verificar cálculo (5 * 4 = 20)
    values = lead_resp["field_values"]
    val_total = next(v for v in values if v["field_id"] == f_total["id"])
    
    # El backend debió sobreescribir el 1 con 20.0
    assert float(val_total["value"]) == 20.0


def test_calculated_field_arithmetic(api, initial_structure):
    """
    Prueba aritmética simple: Total = Precio * Cantidad
    """
    camp_id = initial_structure["campaign"].id
    
    # 1. Crear campos
    f_precio = api.create_lead_field(camp_id, "Precio", "NUMBER", order=1)
    f_cantidad = api.create_lead_field(camp_id, "Cantidad", "INT", order=2)

    f_total = api.create_lead_field(
        camp_id, 
        "Total", 
        "CALCULATED",
        calculation_expression="Precio * Cantidad"
    )

    # 2. Crear Lead
    lead_resp = api.create_lead(camp_id, [
        {"field_id": f_precio["id"], "value": 10.5},
        {"field_id": f_cantidad["id"], "value": 4}
    ])
    
    # 3. Verificar cálculo (10.5 * 4 = 42.0)
    values = lead_resp["field_values"]
    val_total = next(v for v in values if v["field_id"] == f_total["id"])
    assert float(val_total["value"]) == 42.0


def test_calculated_field_logic_and_text(api, initial_structure):
    """
    Prueba lógica compleja: IF + Concatenación
    Fórmula: IF(Edad >= 18, "Mayor: " & Nombre, "Menor")
    """
    camp_id = initial_structure["campaign"].id
    
    f_nombre = api.create_lead_field(camp_id, "Nombre", "STRING")
    f_edad = api.create_lead_field(camp_id, "Edad", "INT")

    f_estado = api.create_lead_field(
        camp_id, 
        "Estado", 
        "CALCULATED", 
        calculation_expression='IF(Edad >= 18, "Mayor: " & Nombre, "Menor")'
    )

    # Caso 1: Mayor
    res1 = api.create_lead(camp_id, [
        {"field_id": f_nombre["id"], "value": "Juan"},
        {"field_id": f_edad["id"], "value": 20}
    ])
    val1 = next(v for v in res1["field_values"] if v["field_id"] == f_estado["id"])
    assert val1["value"] == "Mayor: Juan"

    # Caso 2: Menor
    res2 = api.create_lead(camp_id, [
        {"field_id": f_nombre["id"], "value": "Pedrito"},
        {"field_id": f_edad["id"], "value": 10}
    ])
    val2 = next(v for v in res2["field_values"] if v["field_id"] == f_estado["id"])
    assert val2["value"] == "Menor"


def test_calculated_field_cleaning_functions(api, initial_structure):
    """
    Prueba las funciones de limpieza: TRIM, UPPER, PROPER
    """
    camp_id = initial_structure["campaign"].id
    
    f_sucio = api.create_lead_field(camp_id, "InputSucio", "STRING")

    # Campo que limpia: PROPER(TRIM(InputSucio))
    # Ej: "  juan PEREZ  " -> "Juan Perez"
    f_limpio = api.create_lead_field(
        camp_id, 
        "InputLimpio", 
        "CALCULATED", 
        calculation_expression='PROPER(TRIM(InputSucio))'
    )

    res = api.create_lead(camp_id, [
        {"field_id": f_sucio["id"], "value": "  juan PEREZ  "}
    ])
    
    val_limpio = next(v for v in res["field_values"] if v["field_id"] == f_limpio["id"])
    assert val_limpio["value"] == "Juan Perez"