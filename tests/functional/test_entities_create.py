import pytest
import random

def test_create_full_hierarchy_flow(api):
    """
    Prueba la creación en cadena: Org -> Workspace -> Campaign -> Field
    Esto valida la integridad referencial y que los POST funcionen bajo el 
    nuevo esquema Multi-Tenant.
    """
    rnd = random.randint(1000, 9999)

    # 1. Organization
    res_org = api.create_organization(name=f"Org Test {rnd}")
    org_id = res_org["id"]

    # TRUCO MÁGICO: Actualizamos el ID del tenant en el helper. 
    # Así, las siguientes llamadas inyectarán el header de ESTA nueva organización.
    api.org_id = org_id

    # 2. Workspace
    res_ws = api.create_workspace(name=f"WS Test {rnd}")
    ws_id = res_ws["id"]

    # 3. Campaign
    res_camp = api.create_campaign(workspace_id=ws_id, name=f"Camp {rnd}")
    camp_id = res_camp["id"]

    # 4. Lead Field
    res_field = api.create_lead_field(
        campaign_id=camp_id, 
        name="Campo Test", 
        field_type_code="STRING", 
        section_id=1, 
        expected_status=200
    )
    assert res_field["id"] is not None


def test_create_independent_entities(api, initial_structure):
    """
    Prueba entidades que no dependen estrictamente de la jerarquía principal
    o que usan datos del fixture.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Nomenclator
    # NOTA: Ya no enviamos "organization_id", el backend lo extrae de api.headers
    nom_payload = {"name": "Nomenclador Test"}
    res_nom = api.client.post("/nomenclators/", json=nom_payload, headers=api.headers)
    assert res_nom.status_code in [200, 201], f"Fallo Nomenclator: {res_nom.text}"

    # 2. Validation Rule (Manual)
    # Creamos un campo rápido para asignarle la regla usando el helper
    f_res = api.create_lead_field(
        campaign_id=camp_id, 
        name="FieldParaRegla", 
        field_type_code="INT"
    )
    field_id = f_res["id"]

    # Usamos el helper para crear la regla (ya no requiere org_id en los parámetros ni payload)
    res_rule = api.create_rule(
        field_id=field_id,
        name="Regla Test",
        expression="value > 10",
        error_msg="Error",
        expected_status=200
    )
    
    assert res_rule["id"] is not None