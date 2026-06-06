import pytest
from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState


# =============================================================================
# HELPERS
# =============================================================================

def simulate(api, campaign_id, values):
    """Shorthand para POST /leads/simulate."""
    return api.client.post(
        "/leads/simulate",
        json={"campaign_id": campaign_id, "values": values},
        headers=api.headers,
    )


# =============================================================================
# 1. ESTRUCTURA DE RESPUESTA
# =============================================================================

def test_simulate_response_structure(api, db_session, initial_structure):
    """
    El endpoint debe retornar 200 y un objeto con todos los campos
    que exige LeadResponse: id, active, campaign_id, organization_id,
    current_state_id, current_state, field_values, tags, contact_state.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f = LeadField(
        name="Nombre",
        field_type_code="STRING",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f)
    db_session.commit()

    res = simulate(api, camp_id, [{"field_id": f.id, "value": "Test"}])

    assert res.status_code == 200, res.text
    data = res.json()

    # Campos raíz requeridos
    assert "id" in data
    assert "active" in data
    assert "campaign_id" in data
    assert "organization_id" in data
    assert "current_state_id" in data
    assert "current_state" in data
    assert "field_values" in data
    assert "tags" in data
    assert "contact_state" in data  # puede ser None, pero debe estar

    # La simulación no debe guardar en DB → id negativo o ficticio
    assert data["id"] < 0

    # current_state debe tener los campos de LeadStateResponse
    cs = data["current_state"]
    for key in ("id", "active", "name", "category", "is_initial", "lead_flow_id"):
        assert key in cs, f"Falta '{key}' en current_state"

    assert cs["is_initial"] is True
    assert data["current_state_id"] == cs["id"]
    assert data["tags"] == []


# =============================================================================
# 2. NO PERSISTE EN BASE DE DATOS
# =============================================================================

def test_simulate_does_not_persist(api, db_session, initial_structure):
    """
    Después de simular, no debe existir ningún Lead real en la campaña.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f = LeadField(
        name="Email",
        field_type_code="STRING",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f)
    db_session.commit()

    res = simulate(api, camp_id, [{"field_id": f.id, "value": "test@mail.com"}])
    assert res.status_code == 200

    leads_en_db = db_session.query(Lead).filter_by(campaign_id=camp_id).count()
    assert leads_en_db == 0


# =============================================================================
# 3. CAMPO REQUERIDO FALTANTE → 400
# =============================================================================

def test_simulate_missing_required_field_returns_400(api, db_session, initial_structure):
    """
    Si falta un campo requerido, el simulate debe retornar 400 igual que create,
    NO un 500 por falta de serialización.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f_req = LeadField(
        name="DNI",
        field_type_code="STRING",
        campaign_id=camp_id,
        required=True,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f_req)
    db_session.commit()

    res = simulate(api, camp_id, [])  # valores vacíos → DNI falta

    assert res.status_code == 400
    errors = res.json().get("detail", [])
    assert any("obligatorio" in str(e).lower() or "required" in str(e).lower() or "DNI" in str(e) for e in errors)


# =============================================================================
# 4. TIPO INVÁLIDO → 400
# =============================================================================

def test_simulate_invalid_type_returns_400(api, db_session, initial_structure):
    """
    Un campo INT que recibe un decimal debe retornar 400, no 500.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f_int = LeadField(
        name="Edad",
        field_type_code="INT",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f_int)
    db_session.commit()

    res = simulate(api, camp_id, [{"field_id": f_int.id, "value": 25.7}])

    assert res.status_code == 400
    assert "espera" in res.text.lower() or "entero" in res.text.lower() or "int" in res.text.lower()


# =============================================================================
# 5. REGLA DE VALIDACIÓN APLICADA
# =============================================================================

def test_simulate_validation_rule_rejects_invalid_value(api, initial_structure):
    """
    El simulate debe rechazar un valor que viola la regla ONLY_DIGITS del template DNI_ARG.
    """
    camp_id = initial_structure["campaign_id"]

    field_data = api.create_lead_field_from_template(
        campaign_id=camp_id,
        template_code="DNI_ARG",
        required=True,
        expected_status=200,
    )
    field_id = field_data["id"]

    res = simulate(api, camp_id, [{"field_id": field_id, "value": "ABC-INVALID"}])
    assert res.status_code == 400


def test_simulate_validation_rule_accepts_valid_value(api, initial_structure):
    """
    El simulate debe aceptar un valor que cumple la regla ONLY_DIGITS del template DNI_ARG.
    """
    camp_id = initial_structure["campaign_id"]

    field_data = api.create_lead_field_from_template(
        campaign_id=camp_id,
        template_code="DNI_ARG",
        required=True,
        expected_status=200,
    )
    field_id = field_data["id"]

    res = simulate(api, camp_id, [{"field_id": field_id, "value": "12345678"}])
    assert res.status_code == 200


# =============================================================================
# 6. CAMPO CALCULADO EVALUADO
# =============================================================================

def test_simulate_calculated_field_evaluated(api, db_session, initial_structure):
    """
    Un campo CALCULATED debe mostrar el resultado de la fórmula en la simulación,
    no el valor enviado (que se ignora).
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f_precio = LeadField(
        name="Precio",
        field_type_code="NUMBER",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    f_cantidad = LeadField(
        name="Cantidad",
        field_type_code="INT",
        campaign_id=camp_id,
        order=2,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add_all([f_precio, f_cantidad])
    db_session.flush()

    f_total = LeadField(
        name="Total",
        field_type_code="CALCULATED",
        calculation_expression="Precio * Cantidad",
        campaign_id=camp_id,
        order=3,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
        required=False,
        is_primary=False,
    )
    db_session.add(f_total)
    db_session.commit()

    res = simulate(api, camp_id, [
        {"field_id": f_precio.id, "value": "100"},
        {"field_id": f_cantidad.id, "value": "3"},
    ])

    assert res.status_code == 200
    fvs = {v["field_id"]: v["value"] for v in res.json()["field_values"]}
    assert fvs.get(f_total.id) is not None
    assert float(fvs[f_total.id]) == pytest.approx(300.0)


# =============================================================================
# 7. FIELD_ID INEXISTENTE → 400
# =============================================================================

def test_simulate_unknown_field_id_returns_400(api, db_session, initial_structure):
    """
    Enviar un field_id que no existe en la campaña debe retornar 400.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]

    f = LeadField(
        name="Nombre",
        field_type_code="STRING",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f)
    db_session.commit()

    res = simulate(api, camp_id, [{"field_id": 999999, "value": "Intruso"}])

    assert res.status_code == 400


# =============================================================================
# 8. CAMPAÑA SIN ESTADO INICIAL → 400 (no 500)
# =============================================================================

def test_simulate_campaign_without_initial_state_returns_400(api, db_session, initial_structure):
    """
    Si la campaña no tiene estado inicial configurado, simulate debe
    retornar 400 con mensaje claro, no un 500 por KeyError o AttributeError.
    """
    from app.models.campaign import Campaign

    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    ws_id = initial_structure["workspace_id"]

    # Lead flow nuevo sin estados (el de initial_structure ya tiene estados)
    empty_flow = LeadFlow(name="Flow Sin Estados", organization_id=org_id)
    db_session.add(empty_flow)
    db_session.flush()

    camp_empty = Campaign(
        name="Campaña Sin Estado",
        workspace_id=ws_id,
        lead_flow_id=empty_flow.id,
        organization_id=org_id,
    )
    db_session.add(camp_empty)
    db_session.flush()

    f = LeadField(
        name="Campo",
        field_type_code="STRING",
        campaign_id=camp_empty.id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f)
    db_session.commit()

    res = simulate(api, camp_empty.id, [{"field_id": f.id, "value": "Test"}])

    assert res.status_code == 400
    assert res.status_code != 500


# =============================================================================
# 9. CURRENT_STATE CORRESPONDE AL ESTADO INICIAL DE LA CAMPAÑA
# =============================================================================

def test_simulate_current_state_matches_campaign_initial_state(api, db_session, initial_structure):
    """
    El current_state devuelto por simulate debe coincidir exactamente
    con el estado marcado como is_initial=True del lead_flow de la campaña.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    lead_flow_id = initial_structure["lead_flow_id"]

    # Estado inicial de referencia en la DB
    initial_state = (
        db_session.query(LeadState)
        .filter_by(lead_flow_id=lead_flow_id, is_initial=True)
        .first()
    )
    assert initial_state is not None, "El fixture no tiene estado inicial"

    f = LeadField(
        name="Apellido",
        field_type_code="STRING",
        campaign_id=camp_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
    )
    db_session.add(f)
    db_session.commit()

    res = simulate(api, camp_id, [{"field_id": f.id, "value": "García"}])

    assert res.status_code == 200
    data = res.json()

    assert data["current_state_id"] == initial_state.id
    assert data["current_state"]["id"] == initial_state.id
    assert data["current_state"]["name"] == initial_state.name
    assert data["current_state"]["is_initial"] is True
