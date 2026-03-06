import pytest
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
    
    # Retornamos un diccionario con IDs puros
    return {
        "campaign_id": camp.id, 
        "workspace_id": ws.id, 
        "org_id": org.id,
        "state_initial_id": state_new.id,
        "state_contact_id": state_contact.id,
        "state_won_id": state_won.id,
        "lead_flow_id": lead_flow.id
    }

@pytest.fixture(scope="function")
def initial_fields(db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    
    f_nombre = LeadField(
        name="Nombre", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        required=True, 
        order=1, 
        lead_field_section_id=1, 
        organization_id=org_id,
        active=True
    )
    f_edad = LeadField(
        name="Edad", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        required=False, 
        order=2, 
        lead_field_section_id=1, 
        organization_id=org_id,
        active=True
    )
    
    db_session.add_all([f_nombre, f_edad])
    db_session.commit()
    
    # Retornamos un diccionario con IDs puros
    return {"nombre_id": f_nombre.id, "edad_id": f_edad.id, "campaign_id": camp_id, "org_id": org_id}