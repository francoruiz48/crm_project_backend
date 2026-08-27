import pytest
from app.models.lead_field_section import LeadFieldSection
from app.models.lead_field_type import LeadFieldType
from app.models.lead_field import LeadField
from app.models.campaign import Campaign
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.models.workspace import Workspace
from app.models.organization import Organization

@pytest.fixture(scope="function")
def initial_structure(db_session):
    org = Organization(name="Test org", description="Testing")
    db_session.add(org)
    db_session.flush()

    ws = Workspace(name="Test WS", description="Testing", organization_id=org.id)
    db_session.add(ws)
    db_session.flush()

    lead_flow = LeadFlow(name="Test Lead Flow", organization_id=org.id)
    db_session.add(lead_flow)
    db_session.flush()

    camp = Campaign(name="Test Campaign", workspace_id=ws.id, lead_flow_id=lead_flow.id, organization_id=org.id)
    db_session.add(camp)
    db_session.flush()

    section = LeadFieldSection(name="Información básica", organization_id=org.id)
    db_session.add(section)
    db_session.flush()
    
    # 1. Creamos 3 estados (Inicial, Intermedio, Final)
    state_new = LeadState(
        lead_flow_id=lead_flow.id, organization_id=org.id, 
        name="Nuevo", category="OPEN", is_initial=True, order=1
    )
    state_contact = LeadState(
        lead_flow_id=lead_flow.id, organization_id=org.id, 
        name="En Contacto", category="OPEN", is_initial=False, order=2
    )
    state_won = LeadState(
        lead_flow_id=lead_flow.id, organization_id=org.id, 
        name="Ganado", category="WON", is_initial=False, order=None 
    )

    db_session.add_all([state_new, state_contact, state_won])
    db_session.flush()

    trans_1 = LeadStateTransition(lead_flow_id=lead_flow.id, from_state_id=state_new.id, to_state_id=state_contact.id)
    trans_2 = LeadStateTransition(lead_flow_id=lead_flow.id, from_state_id=state_contact.id, to_state_id=state_won.id)
    
    # Hacemos commit para asegurar todo en la DB
    db_session.add_all([trans_1, trans_2])

    # Hacemos commit para asegurar todo en la DB
    db_session.commit()

    # Devolvemos public_uuid (str) para todo lo que viaja en el BODY de un request de la API
    # real -- desde Fase 1-4 (ver backend/AGENTS.md §18 y siguientes) casi todos los endpoints
    # esperan uuid, no el id interno. Este fixture nunca se actualizó cuando se hizo esa
    # migración, así que hasta ahora mandaba ints donde la API espera texto (422 "Se espera un
    # valor de texto"), rompiendo la gran mayoría de los tests funcionales (ver
    # backend/AGENTS.md §18-novies).
    #
    # `org_id` es la ÚNICA excepción y se queda como int: no viaja en el body, se usa para el
    # header X-Organization-Id (ver ApiClient._inject_context en tests/helpers/api_helpers.py),
    # y ese header sigue siendo un int nativo en el backend (core/security.py:
    # `x_organization_id: Optional[int] = Header(...)`) -- nunca se migró a uuid porque
    # identifica al tenant activo, no un recurso puntual.
    return {
        "campaign_id": camp.public_uuid,
        "workspace_id": ws.public_uuid,
        "org_id": org.id,
        "section_id": section.public_uuid,
        "state_initial_id": state_new.public_uuid,
        "state_contact_id": state_contact.public_uuid,
        "state_won_id": state_won.public_uuid,
        "lead_flow_id": lead_flow.public_uuid
    }

@pytest.fixture(scope="function")
def initial_fields(db_session, initial_structure):
    camp_uuid = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_uuid = initial_structure["section_id"]

    # initial_structure ahora devuelve public_uuid para campaign_id/section_id (ver comentario
    # ahí), pero acá necesitamos los ids internos (int) para el INSERT crudo de LeadField
    # (organization_id/campaign_id/lead_field_section_id son columnas Integer/FK reales).
    camp_id = db_session.query(Campaign.id).filter_by(public_uuid=camp_uuid).scalar()
    section_id = db_session.query(LeadFieldSection.id).filter_by(public_uuid=section_uuid).scalar()

    f_nombre = LeadField(
        name="Nombre", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        required=True, 
        order=1, 
        lead_field_section_id=section_id, 
        organization_id=org_id,
        active=True
    )
    f_edad = LeadField(
        name="Edad", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        required=False, 
        order=2, 
        lead_field_section_id=section_id, 
        organization_id=org_id,
        active=True
    )
    
    db_session.add_all([f_nombre, f_edad])
    db_session.commit()

    # Mismo criterio que initial_structure: public_uuid para lo que va en el body de la API,
    # org_id como int (header). campaign_id se pasa tal cual vino (ya es uuid).
    return {"nombre_id": f_nombre.public_uuid, "edad_id": f_edad.public_uuid, "campaign_id": camp_uuid, "org_id": org_id}