"""
org_fixtures.py
===============
Fixtures de organizaciones multi-tenant para tests de aislamiento.

Provee TenantContext: org + owner + member + estructura base completa
(workspace, lead_flow, campaign, section, estado inicial).

Uso:
    def test_algo(client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        with as_user(api_a, ctx_alpha.owner):
            ...
"""
from dataclasses import dataclass

import pytest

from app.models.campaign import Campaign
from app.models.lead_field_section import LeadFieldSection
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.models.organization import Organization
from app.models.workspace import Workspace
from tests.fixtures.user_fixtures import _link_user_to_org, _make_user
from app.models.security_models import User


@dataclass
class TenantContext:
    # Los campos *_id son el id interno (uso directo en queries/ORM crudo dentro del test).
    # Los campos *_uuid son el public_uuid correspondiente -- usar estos en URLs/JSON de
    # llamadas HTTP a la API, que desde Fase 2/3 esperan el uuid público, no el id interno
    # (excepto X-Organization-Id / ApiClient(client, org_id), que nunca se migró y sigue
    # siendo int). Agregado 2026-07-28: el fixture original solo exponía los ints, lo que
    # rompía cualquier test que mandara ctx_alpha.campaign_id/workspace_id/etc. directo en
    # una llamada real a la API (ver backend/AGENTS.md).
    org_id: int
    org_uuid: str
    owner: User
    member: User
    workspace_id: int
    workspace_uuid: str
    campaign_id: int
    campaign_uuid: str
    lead_flow_id: int
    lead_flow_uuid: str
    section_id: int
    section_uuid: str
    state_initial_id: int
    state_initial_uuid: str
    state_contact_id: int
    state_contact_uuid: str


def _build_tenant(db_session, name: str, suffix: str) -> TenantContext:
    """Crea una organización completa con usuarios y estructura base."""
    org = Organization(name=name, description=f"Tenant {suffix} para tests")
    db_session.add(org)
    db_session.flush()

    owner = _make_user(db_session, f"Owner {suffix}", f"owner_{suffix.lower()}@test.com")
    _link_user_to_org(db_session, owner, org.id, is_owner=True)

    member = _make_user(db_session, f"Member {suffix}", f"member_{suffix.lower()}@test.com")
    _link_user_to_org(db_session, member, org.id, is_owner=False)

    ws = Workspace(name=f"WS {suffix}", description="Testing", organization_id=org.id)
    db_session.add(ws)
    db_session.flush()

    lf = LeadFlow(name=f"Flujo {suffix}", organization_id=org.id)
    db_session.add(lf)
    db_session.flush()

    camp = Campaign(
        name=f"Campaign {suffix}",
        workspace_id=ws.id,
        lead_flow_id=lf.id,
        organization_id=org.id,
    )
    db_session.add(camp)
    db_session.flush()

    section = LeadFieldSection(name="General", organization_id=org.id)
    db_session.add(section)
    db_session.flush()

    state_new = LeadState(
        lead_flow_id=lf.id, organization_id=org.id,
        name="Nuevo", category="OPEN", is_initial=True, order=1,
    )
    state_contact = LeadState(
        lead_flow_id=lf.id, organization_id=org.id,
        name="En Contacto", category="OPEN", is_initial=False, order=2,
    )
    db_session.add_all([state_new, state_contact])
    db_session.flush()

    trans = LeadStateTransition(
        lead_flow_id=lf.id,
        from_state_id=state_new.id,
        to_state_id=state_contact.id,
    )
    db_session.add(trans)
    db_session.commit()

    return TenantContext(
        org_id=org.id,
        org_uuid=org.public_uuid,
        owner=owner,
        member=member,
        workspace_id=ws.id,
        workspace_uuid=ws.public_uuid,
        campaign_id=camp.id,
        campaign_uuid=camp.public_uuid,
        lead_flow_id=lf.id,
        lead_flow_uuid=lf.public_uuid,
        section_id=section.id,
        section_uuid=section.public_uuid,
        state_initial_id=state_new.id,
        state_initial_uuid=state_new.public_uuid,
        state_contact_id=state_contact.id,
        state_contact_uuid=state_contact.public_uuid,
    )


@pytest.fixture
def ctx_alpha(db_session) -> TenantContext:
    """Tenant Alpha completo: org + owner + member + workspace + campaign + flujo + sección."""
    return _build_tenant(db_session, "Empresa Alpha", "Alpha")


@pytest.fixture
def ctx_beta(db_session) -> TenantContext:
    """Tenant Beta completo: org + owner + member + workspace + campaign + flujo + sección."""
    return _build_tenant(db_session, "Empresa Beta", "Beta")


@pytest.fixture
def member_multi(db_session, ctx_alpha, ctx_beta) -> User:
    """Usuario que pertenece a ambas organizaciones (Alpha y Beta)."""
    user = _make_user(db_session, "Member Multi", "member_multi@test.com")
    _link_user_to_org(db_session, user, ctx_alpha.org_id, is_owner=False)
    _link_user_to_org(db_session, user, ctx_beta.org_id, is_owner=False)
    db_session.commit()
    return user
