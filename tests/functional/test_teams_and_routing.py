"""
test_teams_and_routing.py
=========================
Tests de equipos, permisos de roles (MANAGER/AGENT) y políticas de ruteo.

Usa `as_user` para simular usuarios con distintos roles dentro del equipo.
"""
import pytest
from app.models.team_member import TeamMember
from app.models.team import Team
from app.models.security_models import User
from tests.fixtures.user_fixtures import (
    _make_user, _link_user_to_org, as_user
)


# ---------------------------------------------------------------------------
# Fixture local: dos usuarios en la misma org
# ---------------------------------------------------------------------------

@pytest.fixture
def two_users(db_session, initial_structure, api):
    org_id = initial_structure["org_id"]
    user_a = _make_user(db_session, "Usuario A Manager", f"usera_{org_id}@test.com")
    user_b = _make_user(db_session, "Usuario B Agent",   f"userb_{org_id}@test.com")
    _link_user_to_org(db_session, user_a, org_id)
    _link_user_to_org(db_session, user_b, org_id)
    db_session.commit()
    superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
    return {
        "manager":    user_a,
        "agent":      user_b,
        "org_id":     org_id,
        "superadmin": superadmin,
    }


# ---------------------------------------------------------------------------
# Teams — CRUD y comportamiento automático
# ---------------------------------------------------------------------------

def test_create_team_adds_creator_as_manager(api, db_session):
    """El creador de un equipo queda automáticamente como MANAGER."""
    superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
    team = api.create_team(name="Equipo Auto-Manager")
    assert team["id"] > 0
    db_session.expire_all()
    member = db_session.query(TeamMember).filter_by(
        team_id=team["id"], user_id=superadmin.id, role="MANAGER"
    ).first()
    assert member is not None, "El creador debería ser MANAGER automáticamente."


def test_team_name_must_be_unique_per_org(api):
    api.create_team("Equipo Nombre Unico", expected_status=200)
    api.create_team("Equipo Nombre Unico", expected_status=400)


def test_team_delete_cascades_members(api, db_session):
    team = api.create_team("Equipo Cascade")
    team_id = team["id"]
    db_session.expire_all()
    assert db_session.query(TeamMember).filter_by(team_id=team_id).count() == 1
    api.client.delete(f"/teams/{team_id}?force=true", headers=api.headers)
    db_session.expire_all()
    assert db_session.get(Team, team_id) is None
    assert db_session.query(TeamMember).filter_by(team_id=team_id).count() == 0


def test_team_same_name_different_orgs_allowed(api, db_session):
    org2 = api.create_organization("Segunda Org para nombre")
    old_org_id = api.org_id
    api.create_team("Nombre Compartido")
    api.org_id = org2["id"]
    api.create_team("Nombre Compartido")
    api.org_id = old_org_id


def test_duplicate_member_rejected(api, db_session):
    """No se puede agregar al mismo usuario dos veces al mismo equipo."""
    superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
    team = api.create_team("Equipo Duplicado")
    # El superadmin ya está como MANAGER (auto-agregado al crear el equipo)
    api.add_team_member(team["id"], user_id=superadmin.id, role="AGENT", expected_status=400)


# ---------------------------------------------------------------------------
# Permisos de roles: AGENT vs MANAGER
# ---------------------------------------------------------------------------

def test_agent_cannot_add_manager(api, two_users):
    team = api.create_team("Equipo Roles 1")
    team_id = team["id"]
    api.add_team_member(team_id, two_users["agent"].id, role="AGENT")

    with as_user(api, two_users["agent"]):
        resp = api.client.post(
            "/team_members/",
            json={"team_id": team_id, "user_id": two_users["manager"].id, "role": "MANAGER"},
            headers=api.headers,
        )
    assert resp.status_code == 403


def test_agent_cannot_self_promote_to_manager(api, two_users):
    team = api.create_team("Equipo Roles 2")
    team_id = team["id"]
    member = api.add_team_member(team_id, two_users["agent"].id, role="AGENT")

    with as_user(api, two_users["agent"]):
        resp = api.client.put(
            f"/team_members/{member['id']}",
            json={"role": "MANAGER"},
            headers=api.headers,
        )
    assert resp.status_code == 403


def test_manager_can_add_agent(api, two_users):
    team = api.create_team("Equipo Roles 3")
    team_id = team["id"]
    api.add_team_member(team_id, two_users["manager"].id, role="MANAGER")

    with as_user(api, two_users["manager"]):
        resp = api.client.post(
            "/team_members/",
            json={"team_id": team_id, "user_id": two_users["agent"].id, "role": "AGENT"},
            headers=api.headers,
        )
    assert resp.status_code in (200, 201)


def test_manager_can_promote_agent_to_manager(api, two_users):
    team = api.create_team("Equipo Roles 4")
    team_id = team["id"]
    api.add_team_member(team_id, two_users["manager"].id, role="MANAGER")
    member = api.add_team_member(team_id, two_users["agent"].id, role="AGENT")

    with as_user(api, two_users["manager"]):
        resp = api.client.put(
            f"/team_members/{member['id']}",
            json={"role": "MANAGER"},
            headers=api.headers,
        )
    assert resp.status_code == 200
    assert resp.json()["role"] == "MANAGER"


def test_agent_cannot_remove_team_member(api, two_users):
    """Un AGENT no puede eliminar miembros del equipo."""
    team = api.create_team("Equipo Roles 5")
    team_id = team["id"]
    member = api.add_team_member(team_id, two_users["agent"].id, role="AGENT")

    with as_user(api, two_users["agent"]):
        resp = api.client.delete(
            f"/team_members/{member['id']}",
            headers=api.headers,
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Políticas de ruteo — lógica de condiciones
# ---------------------------------------------------------------------------

def test_routing_policy_simple_match_and_fallback(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo VIP")
    f_sueldo = api.create_lead_field(camp_id, "Sueldo", "INT")

    api.create_routing_policy(
        name           = "Sueldo exacto VIP",
        target_team_id = team["id"],
        conditions     = [{"lead_field_id": f_sueldo["id"], "operator": "eq",
                           "value_str": "5000", "position": 0}],
        priority       = 1,
        campaign_id    = camp_id,
    )

    lead_vip    = api.create_lead(camp_id, [{"field_id": f_sueldo["id"], "value": 5000}])
    lead_normal = api.create_lead(camp_id, [{"field_id": f_sueldo["id"], "value": 1000}])

    assert lead_vip["team_id"]    == team["id"]
    assert lead_normal["team_id"] is None


def test_routing_policy_string_ilike(api, initial_structure):
    camp_id  = initial_structure["campaign_id"]
    team     = api.create_team("Equipo Buenos Aires")
    f_ciudad = api.create_lead_field(camp_id, "Ciudad", "STRING")

    api.create_routing_policy(
        name           = "Ciudad Buenos Aires",
        target_team_id = team["id"],
        conditions     = [{"lead_field_id": f_ciudad["id"], "operator": "ilike",
                           "value_str": "buenos aires", "position": 0}],
        priority       = 1,
        campaign_id    = camp_id,
    )

    match    = api.create_lead(camp_id, [{"field_id": f_ciudad["id"], "value": "BUENOS AIRES"}])
    no_match = api.create_lead(camp_id, [{"field_id": f_ciudad["id"], "value": "Rosario"}])

    assert match["team_id"]    == team["id"]
    assert no_match["team_id"] is None


def test_routing_policy_range_inclusive(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Rango")
    f_monto = api.create_lead_field(camp_id, "Monto", "INT")

    api.create_routing_policy(
        name           = "Monto en rango",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_monto["id"],
            "operator_min": "gte", "value_min": "1000",
            "operator_max": "lte", "value_max": "5000",
            "position": 0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    in_range  = api.create_lead(camp_id, [{"field_id": f_monto["id"], "value": 1000}])
    out_range = api.create_lead(camp_id, [{"field_id": f_monto["id"], "value": 5001}])
    boundary  = api.create_lead(camp_id, [{"field_id": f_monto["id"], "value": 5000}])

    assert in_range["team_id"]  == team["id"]
    assert out_range["team_id"] is None
    assert boundary["team_id"]  == team["id"]


def test_routing_policy_range_exclusive_lower(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Rango Exclusivo")
    f_val   = api.create_lead_field(camp_id, "Puntaje", "INT")

    api.create_routing_policy(
        name           = "Puntaje mayor estricto",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_val["id"],
            "operator_min": "gt",  "value_min": "100",
            "operator_max": "lte", "value_max": "200",
            "position": 0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    exact_boundary = api.create_lead(camp_id, [{"field_id": f_val["id"], "value": 100}])
    above_boundary = api.create_lead(camp_id, [{"field_id": f_val["id"], "value": 101}])

    assert exact_boundary["team_id"] is None
    assert above_boundary["team_id"] == team["id"]


def test_routing_policy_selector_in(api, db_session, initial_structure):
    from app.models.nomenclator import Nomenclator
    from app.models.nomenclator_item import NomenclatorItem

    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]

    nom = Nomenclator(name="Zonas Test In", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    item_norte = NomenclatorItem(nomenclator_id=nom.id, value="Norte", organization_id=org_id)
    item_sur   = NomenclatorItem(nomenclator_id=nom.id, value="Sur",   organization_id=org_id)
    db_session.add_all([item_norte, item_sur])
    db_session.commit()

    team   = api.create_team("Equipo Norte/Sur")
    f_zona = api.create_lead_field(
        camp_id, "Zona", "SELECTOR", subtype_code="SELECTOR_SIMPLE", nomenclator_id=nom.id
    )

    api.create_routing_policy(
        name           = "Zona Norte o Sur",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_zona["id"],
            "operator":    "in",
            "value_list":  [str(item_norte.id), str(item_sur.id)],
            "position": 0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    match    = api.create_lead(camp_id, [{"field_id": f_zona["id"], "value": item_norte.id}])
    no_match = api.create_lead(camp_id, [])

    assert match["team_id"]    == team["id"]
    assert no_match["team_id"] is None


def test_routing_policy_selector_eq_strict(api, db_session, initial_structure):
    from app.models.nomenclator import Nomenclator
    from app.models.nomenclator_item import NomenclatorItem

    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]

    nom = Nomenclator(name="Tags Strict", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    tag_a = NomenclatorItem(nomenclator_id=nom.id, value="TagA", organization_id=org_id)
    tag_b = NomenclatorItem(nomenclator_id=nom.id, value="TagB", organization_id=org_id)
    db_session.add_all([tag_a, tag_b])
    db_session.commit()

    team  = api.create_team("Equipo Strict")
    f_tag = api.create_lead_field(
        camp_id, "Tags", "SELECTOR", subtype_code="SELECTOR_MULTIPLE", nomenclator_id=nom.id
    )

    api.create_routing_policy(
        name           = "Solo TagA y TagB exactos",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_tag["id"],
            "operator":    "eq_strict",
            "value_list":  [str(tag_a.id), str(tag_b.id)],
            "position": 0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    exact  = api.create_lead(camp_id, [{"field_id": f_tag["id"], "value": [tag_a.id, tag_b.id]}])
    only_a = api.create_lead(camp_id, [{"field_id": f_tag["id"], "value": tag_a.id}])

    assert exact["team_id"]  == team["id"]
    assert only_a["team_id"] is None


def test_routing_policy_and_both_must_match(api, initial_structure):
    camp_id  = initial_structure["campaign_id"]
    team     = api.create_team("Equipo AND")
    f_ciudad = api.create_lead_field(camp_id, "Ciudad AND", "STRING")
    f_edad   = api.create_lead_field(camp_id, "Edad AND",   "INT")

    api.create_routing_policy(
        name             = "Ciudad Mendoza Y Edad >= 25",
        target_team_id   = team["id"],
        logical_operator = "AND",
        conditions       = [
            {"lead_field_id": f_ciudad["id"], "operator": "eq",  "value_str": "Mendoza", "position": 0},
            {"lead_field_id": f_edad["id"],   "operator": "gte", "value_str": "25",       "position": 1},
        ],
        priority    = 1,
        campaign_id = camp_id,
    )

    both_match = api.create_lead(camp_id, [
        {"field_id": f_ciudad["id"], "value": "Mendoza"},
        {"field_id": f_edad["id"],   "value": 30},
    ])
    only_city  = api.create_lead(camp_id, [
        {"field_id": f_ciudad["id"], "value": "Mendoza"},
        {"field_id": f_edad["id"],   "value": 20},
    ])

    assert both_match["team_id"] == team["id"]
    assert only_city["team_id"]  is None


def test_routing_policy_or_any_condition_matches(api, initial_structure):
    camp_id  = initial_structure["campaign_id"]
    team     = api.create_team("Equipo OR")
    f_ciudad = api.create_lead_field(camp_id, "Ciudad OR",  "STRING")
    f_vip    = api.create_lead_field(camp_id, "Es VIP OR",  "BOOL")

    api.create_routing_policy(
        name             = "Ciudad Mendoza O Es VIP",
        target_team_id   = team["id"],
        logical_operator = "OR",
        conditions       = [
            {"lead_field_id": f_ciudad["id"], "operator": "eq", "value_str": "Mendoza", "position": 0},
            {"lead_field_id": f_vip["id"],    "operator": "eq", "value_str": "true",    "position": 1},
        ],
        priority    = 1,
        campaign_id = camp_id,
    )

    via_ciudad = api.create_lead(camp_id, [{"field_id": f_ciudad["id"], "value": "Mendoza"}])
    via_vip    = api.create_lead(camp_id, [{"field_id": f_vip["id"],    "value": True}])
    no_match   = api.create_lead(camp_id, [{"field_id": f_ciudad["id"], "value": "Córdoba"}])

    assert via_ciudad["team_id"] == team["id"]
    assert via_vip["team_id"]    == team["id"]
    assert no_match["team_id"]   is None


def test_routing_policy_priority_lower_wins(api, initial_structure):
    camp_id   = initial_structure["campaign_id"]
    team_alta = api.create_team("Equipo Alta Prioridad")
    team_baja = api.create_team("Equipo Baja Prioridad")
    f_score   = api.create_lead_field(camp_id, "Score Prio", "INT")

    api.create_routing_policy(
        name="Score >= 50 (prio 2)", target_team_id=team_baja["id"],
        conditions=[{"lead_field_id": f_score["id"], "operator": "gte",
                     "value_str": "50", "position": 0}],
        priority=2, campaign_id=camp_id,
    )
    api.create_routing_policy(
        name="Score >= 50 (prio 1)", target_team_id=team_alta["id"],
        conditions=[{"lead_field_id": f_score["id"], "operator": "gte",
                     "value_str": "50", "position": 0}],
        priority=1, campaign_id=camp_id,
    )

    lead = api.create_lead(camp_id, [{"field_id": f_score["id"], "value": 80}])
    assert lead["team_id"] == team_alta["id"]


def test_routing_policy_priority_unique_per_scope(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Prio Dup")
    f_x     = api.create_lead_field(camp_id, "Campo Prio", "INT")

    api.create_routing_policy(
        name="Política prio 1", target_team_id=team["id"],
        conditions=[{"lead_field_id": f_x["id"], "operator": "eq",
                     "value_str": "1", "position": 0}],
        priority=1, campaign_id=camp_id,
    )
    api.create_routing_policy(
        name="Política prio 1 bis", target_team_id=team["id"],
        conditions=[{"lead_field_id": f_x["id"], "operator": "eq",
                     "value_str": "2", "position": 0}],
        priority=1, campaign_id=camp_id,
        expected_status=400,
    )


def test_routing_policy_native_field_current_state(api, initial_structure):
    camp_id       = initial_structure["campaign_id"]
    initial_state = initial_structure["state_initial_id"]
    team          = api.create_team("Equipo Estado Inicial")

    api.create_routing_policy(
        name           = "Lead en estado inicial",
        target_team_id = team["id"],
        conditions     = [{
            "native_field": "current_state_id",
            "operator":     "eq",
            "value_str":    str(initial_state),
            "position": 0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    f_dummy = api.create_lead_field(camp_id, "Dummy Native", "STRING")
    lead    = api.create_lead(camp_id, [{"field_id": f_dummy["id"], "value": "x"}])
    assert lead["team_id"] == team["id"]


def test_agent_cannot_create_routing_policy(api, two_users):
    team = api.create_team("Equipo Policy Perm")
    api.add_team_member(team["id"], two_users["agent"].id, role="AGENT")

    with as_user(api, two_users["agent"]):
        resp = api.client.post(
            "/lead_routing_policies/",
            json={
                "name":             "Política del Agent",
                "target_team_id":   team["id"],
                "priority":         99,
                "logical_operator": "AND",
                "conditions":       [],
            },
            headers=api.headers,
        )
    assert resp.status_code == 403


def test_manager_can_create_routing_policy(api, two_users, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Policy Manager")
    api.add_team_member(team["id"], two_users["manager"].id, role="MANAGER")
    f_x     = api.create_lead_field(camp_id, "Campo Manager Policy", "INT")

    with as_user(api, two_users["manager"]):
        resp = api.client.post(
            "/lead_routing_policies/",
            json={
                "name":             "Política del Manager",
                "target_team_id":   team["id"],
                "priority":         50,
                "logical_operator": "AND",
                "campaign_id":      camp_id,
                "conditions": [{
                    "lead_field_id": f_x["id"],
                    "operator":      "eq",
                    "value_str":     "1",
                    "position":      0,
                }],
            },
            headers=api.headers,
        )
    assert resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Validación de políticas
# ---------------------------------------------------------------------------

def test_validate_policy_rejects_forbidden_field_type(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Validate")

    f_file = api.client.post("/lead_fields/", json={
        "campaign_id":        camp_id,
        "name":               "Archivo Test",
        "field_type_code":    "FILE",
        "field_subtype_code": "FILE_DOCUMENT",
    }, headers=api.headers)

    if f_file.status_code not in (200, 201):
        pytest.skip("No se pudo crear campo FILE para este test")

    f_id = f_file.json()["id"]

    result = api.validate_routing_policy(
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_id,
            "operator":      "eq",
            "value_str":     "algo",
            "position":      0,
        }],
        campaign_id = camp_id,
    )
    assert result["valid"] is False
    assert any("FILE" in e or "permitido" in e or "compatible" in e for e in result["errors"])


def test_validate_policy_detects_team_wrong_org(api, initial_structure):
    org2    = api.create_organization("Org Validate Externa")
    old_id  = api.org_id
    api.org_id = org2["id"]
    team_otro = api.create_team("Equipo Externo")
    api.org_id = old_id

    result = api.validate_routing_policy(
        target_team_id = team_otro["id"],
        conditions     = [],
    )
    assert result["valid"] is False
    assert any("organización" in e.lower() or "equipo" in e.lower() for e in result["errors"])


def test_validate_policy_valid_conditions_returns_true(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Validate OK")
    f_num   = api.create_lead_field(camp_id, "Número Validate", "INT")

    result = api.validate_routing_policy(
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_num["id"],
            "operator":      "gte",
            "value_str":     "100",
            "position":      0,
        }],
        campaign_id = camp_id,
    )
    assert result["valid"] is True
    assert result["errors"] == []


def test_routing_policy_global_applies_to_any_campaign(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Global Policy")
    f_score = api.create_lead_field(camp_id, "Score Global", "INT")

    api.create_routing_policy(
        name           = "Score alto global",
        target_team_id = team["id"],
        conditions     = [{"lead_field_id": f_score["id"], "operator": "gte",
                           "value_str": "90", "position": 0}],
        priority       = 1,
        campaign_id    = None,
    )

    lead = api.create_lead(camp_id, [{"field_id": f_score["id"], "value": 95}])
    assert lead["team_id"] == team["id"]


def test_bulk_assign_leads(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    f_base  = api.create_lead_field(camp_id, "Dato Bulk", "STRING")
    lead_1  = api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "A"}])
    lead_2  = api.create_lead(camp_id, [{"field_id": f_base["id"], "value": "B"}])

    assert lead_1["team_id"] is None

    team     = api.create_team("Equipo Rescate")
    res_bulk = api.bulk_assign(
        lead_ids       = [lead_1["id"], lead_2["id"]],
        target_team_id = team["id"],
    )

    assert len(res_bulk) == 2
    for lead in res_bulk:
        assert lead["team_id"] == team["id"]


def test_workspace_access_rejects_wrong_org_workspace(api, initial_structure):
    org2 = api.create_organization("Org Access Test")
    old_id = api.org_id
    api.org_id = org2["id"]
    ws_otro = api.create_workspace("WS Externo")
    api.org_id = old_id

    team = api.create_team("Equipo Access WS")
    resp = api.client.post(
        "/team_workspace_access/",
        json={"team_id": team["id"], "workspace_id": ws_otro["id"]},
        headers=api.headers,
    )
    assert resp.status_code == 400


def test_campaign_access_rejects_wrong_org_campaign(api, initial_structure):
    org2 = api.create_organization("Org Access Camp Test")
    old_id = api.org_id
    api.org_id = org2["id"]
    ws_otro = api.create_workspace("WS Externo Camp")

    # Crear un flujo para la nueva org (no hereda el de initial_structure)
    resp_flow = api.client.post(
        "/lead_flows/",
        json={"name": "Flujo Externo"},
        headers=api.headers,
    )
    assert resp_flow.status_code == 200
    flow_id = resp_flow.json()["id"]

    camp_otro = api.create_campaign(ws_otro["id"], "Campaña Externa", lead_flow_id=flow_id)
    api.org_id = old_id

    team = api.create_team("Equipo Access Camp")
    resp = api.client.post(
        "/team_campaign_access/",
        json={"team_id": team["id"], "campaign_id": camp_otro["id"]},
        headers=api.headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Nuevas casuísticas
# ---------------------------------------------------------------------------

def test_agent_cannot_remove_team_member(api, two_users):
    """Un AGENT no puede expulsar a otro miembro del equipo."""
    team = api.create_team("Equipo Remove Perm")
    api.add_team_member(team["id"], two_users["agent"].id,   role="AGENT")
    victim = api.add_team_member(team["id"], two_users["manager"].id, role="MANAGER")

    with as_user(api, two_users["agent"]):
        resp = api.client.delete(f"/team_members/{victim['id']}", headers=api.headers)
    assert resp.status_code == 403, "Un AGENT no debería poder eliminar miembros del equipo."


def test_manager_cannot_create_policy_for_another_team(api, two_users, initial_structure):
    """Un MANAGER del equipo A no puede crear políticas para el equipo B."""
    camp_id   = initial_structure["campaign_id"]
    team_own  = api.create_team("Equipo Propio Manager")
    team_otro = api.create_team("Equipo Ajeno Manager")
    api.add_team_member(team_own["id"], two_users["manager"].id, role="MANAGER")
    # two_users["manager"] NO pertenece a team_otro

    f_x = api.create_lead_field(camp_id, "Campo Política Ajena", "INT")

    with as_user(api, two_users["manager"]):
        resp = api.client.post(
            "/lead_routing_policies/",
            json={
                "name":             "Política para equipo ajeno",
                "target_team_id":   team_otro["id"],
                "priority":         98,
                "logical_operator": "AND",
                "campaign_id":      camp_id,
                "conditions": [{
                    "lead_field_id": f_x["id"],
                    "operator":      "eq",
                    "value_str":     "1",
                    "position":      0,
                }],
            },
            headers=api.headers,
        )
    assert resp.status_code == 403, "Un MANAGER no debería poder crear políticas para un equipo al que no pertenece."


def test_validate_policy_rejects_field_from_wrong_campaign(api, initial_structure):
    """
    La validación rechaza un campo que pertenece a otra campaña distinta
    a la campaña de la política.
    """
    camp_id  = initial_structure["campaign_id"]
    flow_id  = initial_structure["lead_flow_id"]

    ws      = api.create_workspace("WS Validación Campo")
    camp2   = api.create_campaign(ws["id"], "Campaign 2 Validación", lead_flow_id=flow_id)
    f_otro  = api.create_lead_field(camp2["id"], "Campo de Otra Campaign", "INT")
    team    = api.create_team("Equipo Campo Inválido")

    result = api.validate_routing_policy(
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_otro["id"],
            "operator":      "eq",
            "value_str":     "1",
            "position":      0,
        }],
        campaign_id = camp_id,
    )
    assert result["valid"] is False
    assert any("campaña" in e.lower() or "campaign" in e.lower() for e in result["errors"]), \
        f"Se esperaba error de campaña incorrecta, se recibió: {result['errors']}"


def test_routing_policy_selector_not_in(api, db_session, initial_structure):
    """SELECTOR not_in: el lead matchea si su valor NO está en la lista."""
    from app.models.nomenclator import Nomenclator
    from app.models.nomenclator_item import NomenclatorItem

    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]

    nom = Nomenclator(name="Zonas NotIn", organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    item_norte = NomenclatorItem(nomenclator_id=nom.id, value="Norte", organization_id=org_id)
    item_sur   = NomenclatorItem(nomenclator_id=nom.id, value="Sur",   organization_id=org_id)
    item_este  = NomenclatorItem(nomenclator_id=nom.id, value="Este",  organization_id=org_id)
    db_session.add_all([item_norte, item_sur, item_este])
    db_session.commit()

    team   = api.create_team("Equipo NotIn")
    f_zona = api.create_lead_field(
        camp_id, "Zona NotIn", "SELECTOR",
        subtype_code="SELECTOR_SIMPLE", nomenclator_id=nom.id,
    )

    api.create_routing_policy(
        name           = "Zona que NO es Norte ni Sur",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_zona["id"],
            "operator":      "not_in",
            "value_list":    [str(item_norte.id), str(item_sur.id)],
            "position":      0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    excluido = api.create_lead(camp_id, [{"field_id": f_zona["id"], "value": item_norte.id}])
    incluido = api.create_lead(camp_id, [{"field_id": f_zona["id"], "value": item_este.id}])

    assert excluido["team_id"] is None,     "Norte está en la lista excluida, no debería rutear."
    assert incluido["team_id"] == team["id"], "Este NO está en la lista excluida, debería rutear."


def test_routing_policy_native_field_assigned_to_user(api, db_session, initial_structure):
    """Routing basado en campo nativo assigned_to_user_id al momento de crear el lead."""
    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]

    agente = _make_user(db_session, "Agente Nativo", f"agente_nativo_{org_id}@test.com")
    _link_user_to_org(db_session, agente, org_id)
    db_session.commit()

    team = api.create_team("Equipo Usuario Nativo")

    api.create_routing_policy(
        name           = "Lead asignado al agente específico",
        target_team_id = team["id"],
        conditions     = [{
            "native_field": "assigned_to_user_id",
            "operator":     "eq",
            "value_str":    str(agente.id),
            "position":     0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    f_dummy       = api.create_lead_field(camp_id, "Dato Asignado", "STRING")
    lead_asignado = api.create_lead(
        camp_id,
        [{"field_id": f_dummy["id"], "value": "x"}],
        assigned_to_user_id=agente.id,
    )
    lead_libre = api.create_lead(camp_id, [{"field_id": f_dummy["id"], "value": "y"}])

    assert lead_asignado["team_id"] == team["id"], "El lead asignado al agente debería rutearse."
    assert lead_libre["team_id"]    is None,        "El lead sin asignar no debería rutearse."


def test_routing_policy_inactive_does_not_route(api, db_session, initial_structure):
    """
    Una política con active=False no debe rutear leads, aunque sus condiciones matcheen.
    Se verifica también que, antes de desactivarla, sí rutea (smoke check).
    """
    from app.models.lead_routing_policy import LeadRoutingPolicy

    camp_id = initial_structure["campaign_id"]
    team    = api.create_team("Equipo Inactivo")
    f_score = api.create_lead_field(camp_id, "Score Inactivo", "INT")

    policy = api.create_routing_policy(
        name           = "Política a desactivar",
        target_team_id = team["id"],
        conditions     = [{
            "lead_field_id": f_score["id"],
            "operator":      "gte",
            "value_str":     "1",
            "position":      0,
        }],
        priority    = 1,
        campaign_id = camp_id,
    )

    # Smoke: con la política activa el lead se rutea
    lead_antes = api.create_lead(camp_id, [{"field_id": f_score["id"], "value": 50}])
    assert lead_antes["team_id"] == team["id"], "La política activa debería rutear."

    # Desactivar directo en DB (active no está expuesto en el schema de update aún)
    db_session.query(LeadRoutingPolicy).filter_by(id=policy["id"]).update({"active": False})
    db_session.commit()

    lead_despues = api.create_lead(camp_id, [{"field_id": f_score["id"], "value": 50}])
    assert lead_despues["team_id"] is None, "La política inactiva NO debería rutear."
