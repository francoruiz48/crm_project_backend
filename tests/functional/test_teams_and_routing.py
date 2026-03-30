import pytest
from app.models.team_member import TeamMember
from app.models.team import Team



def test_team_crud_and_duplicate_members(api, db_session, initial_structure):
    """
    Bloque 1: Verifica la creación de equipos, adición de miembros 
    y el rechazo de miembros duplicados.
    """
    # 1. Crear Equipo
    team = api.create_team(name="Ventas Norte", is_visibility_shared=True)
    assert team["id"] > 0
    assert team["active"] is True

    # 2. Agregar Miembro (Asumimos que el user_id=1 existe por el setup)
    member = api.add_team_member(team["id"], user_id=1, role="MANAGER")
    assert member["role"] == "MANAGER"

    # 3. Intentar agregar el mismo miembro al mismo equipo (Debe fallar 400)
    api.add_team_member(team["id"], user_id=1, role="AGENT", expected_status=400)

    # 4. Borrar Equipo y validar Cascada (TeamMember debe desaparecer)
    api.client.delete(f"/teams/{team['id']}", headers=api.headers)
    db_session.expire_all()
    
    assert db_session.get(Team, team["id"]) is None
    assert db_session.get(TeamMember, member["id"]) is None


def test_routing_rule_custom_field_and_fallback(api, initial_structure):
    """
    Bloque 4: Verifica que un Lead se auto-asigne a un equipo si cumple la regla,
    y que caiga huérfano (None) si no la cumple.
    """
    camp_id = initial_structure["campaign_id"]

    # 1. Setup: Crear Equipo y Campo Custom
    team_vip = api.create_team("Equipo VIP")
    field_sueldo = api.create_lead_field(camp_id, "Sueldo", "INT")

    # 2. Crear Regla de Enrutamiento (Sueldo = 5000 -> Equipo VIP)
    api.create_routing_rule(
        condition_type="CUSTOM_FIELD",
        condition_target_id=field_sueldo["id"],
        condition_value="5000",
        target_team_id=team_vip["id"],
        campaign_id=camp_id
    )

    # 3. Crear Lead MATCH (Debe ir al Equipo VIP)
    lead_vip = api.create_lead(camp_id, [{"field_id": field_sueldo["id"], "value": 5000}])
    assert lead_vip["team_id"] == team_vip["id"], "El motor no asignó el equipo correctamente."

    # 4. Crear Lead FALLBACK (Debe quedar huérfano)
    lead_normal = api.create_lead(camp_id, [{"field_id": field_sueldo["id"], "value": 1000}])
    assert lead_normal["team_id"] is None, "El lead no debería tener equipo."


def test_routing_rule_priority_order(api, initial_structure):
    """
    Bloque 4: Verifica el choque de reglas. El motor debe respetar la regla
    con el 'order' más bajo (mayor prioridad).
    """
    camp_id = initial_structure["campaign_id"]

    # 1. Setup
    team_a = api.create_team("Equipo A (Prioridad)")
    team_b = api.create_team("Equipo B (Secundario)")
    f_provincia = api.create_lead_field(camp_id, "Provincia", "STRING")

    # 2. Crear Regla 1 (Orden 2 - Secundario)
    api.create_routing_rule(
        condition_type="CUSTOM_FIELD",
        condition_target_id=f_provincia["id"],
        condition_value="Mendoza",
        target_team_id=team_b["id"],
        campaign_id=camp_id,
        order=2
    )

    # 3. Crear Regla 2 (Orden 1 - Prioridad) MISMA CONDICIÓN
    api.create_routing_rule(
        condition_type="CUSTOM_FIELD",
        condition_target_id=f_provincia["id"],
        condition_value="Mendoza",
        target_team_id=team_a["id"],
        campaign_id=camp_id,
        order=1
    )

    # 4. Crear Lead -> Debe ser atrapado por la Regla de Orden 1 (Equipo A)
    lead = api.create_lead(camp_id, [{"field_id": f_provincia["id"], "value": "Mendoza"}])
    assert lead["team_id"] == team_a["id"], "No se respetó la prioridad de la regla (Order)."


def test_routing_rule_nomenclator_global(api, initial_structure):
    """
    Bloque 4: Verifica una regla GLOBAL (Nivel Organización) basada en Nomenclador.
    Debe aplicar sin importar en qué campaña se cree el lead.
    """
    camp_id = initial_structure["campaign_id"]

    # 1. Crear Nomenclador y agregar item
    res_nom = api.client.post("/nomenclators/", json={"name": "Zonas"}, headers=api.headers)
    nom_id = res_nom.json()["id"]
    res_item = api.client.post(f"/nomenclator_items/", json={"code": "Sur", "value": "Sur", "nomenclator_id": nom_id}, headers=api.headers)
    item_sur_id = res_item.json()["id"]

    # 2. Crear Equipo y Regla GLOBAL (campaign_id = None)
    team_sur = api.create_team("Ventas Sur")
    api.create_routing_rule(
        condition_type="NOMENCLATOR",
        condition_target_id=nom_id,
        condition_value=str(item_sur_id),
        target_team_id=team_sur["id"],
        campaign_id=None
    )

    # 3. Crear Campo Selector en la Campaña que apunte al nomenclador
    f_zona = api.create_lead_field(camp_id, "Seleccione Zona", "SELECTOR", subtype_code="SELECTOR_SIMPLE", nomenclator_id=nom_id)

    # 4. Crear Lead -> Debe atraparlo la regla global
    lead = api.create_lead(camp_id, [{"field_id": f_zona["id"], "value": item_sur_id}])
    assert lead["team_id"] == team_sur["id"], "La regla global de nomenclador falló."


def test_bulk_assign_leads(api, initial_structure):
    """
    Bloque 5: Verifica la reasignación masiva manual.
    """
    camp_id = initial_structure["campaign_id"]

    # 1. Crear leads huérfanos
    f_base = api.create_lead_field(camp_id, "Dato", "STRING")
    lead_1 = api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "A"}])
    lead_2 = api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "B"}])
    
    assert lead_1["team_id"] is None

    # 2. Crear Equipo y usar Bulk Assign
    team = api.create_team("Equipo Rescate")
    
    # Asumimos que agregaste el endpoint PATCH en tu LeadController
    res_bulk = api.bulk_assign(
        lead_ids=[lead_1["id"], lead_2["id"]],
        target_team_id=team["id"]
    )

    # 3. Validar
    assert len(res_bulk) == 2
    for l in res_bulk:
        assert l["team_id"] == team["id"], "El bulk assign no actualizó el team_id"


