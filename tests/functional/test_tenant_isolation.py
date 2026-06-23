"""
test_tenant_isolation.py
========================
Verifica que los datos de una organización NO son visibles desde otra.

Patrón general: Alpha crea → Beta no lo ve → Alpha sí lo ve.

Usa:
  - ctx_alpha / ctx_beta: TenantContext con org + owner + member + estructura base
  - as_user(api, user): context manager que simula un usuario específico
  - ApiClient(client, org_id): cliente HTTP con cabecera X-Organization-Id
"""
import pytest
from app.core.constans import ADMIN_ORG_ID
from tests.helpers.api_helpers import ApiClient
from tests.fixtures.user_fixtures import as_user
from tests.fixtures.org_fixtures import TenantContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ids(resp) -> list:
    """Extrae IDs de una respuesta que puede ser lista o paginada."""
    data = resp.json()
    if isinstance(data, list):
        return [item["id"] for item in data]
    if isinstance(data, dict) and "items" in data:
        return [item["id"] for item in data["items"]]
    return []


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:

    def test_workspace_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            ws = api_a.create_workspace("WS Privado Alpha")

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/workspaces/", headers=api_b.headers)

        assert ws["id"] not in _ids(resp), "Beta no debería ver el workspace de Alpha"

    def test_workspace_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            ws = api_a.create_workspace("WS Propio Alpha")
            resp = client.get("/workspaces/", headers=api_a.headers)

        assert ws["id"] in _ids(resp)


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

class TestCampaignIsolation:

    def test_campaign_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            camp = api_a.create_campaign(
                workspace_id=ctx_alpha.workspace_id,
                name="Camp Privada Alpha",
                lead_flow_id=ctx_alpha.lead_flow_id,
            )

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/campaigns/", headers=api_b.headers)

        assert camp["id"] not in _ids(resp)

    def test_campaign_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            camp = api_a.create_campaign(
                workspace_id=ctx_alpha.workspace_id,
                name="Camp Propia Alpha",
                lead_flow_id=ctx_alpha.lead_flow_id,
            )
            resp = client.get("/campaigns/", headers=api_a.headers)

        assert camp["id"] in _ids(resp)


# ---------------------------------------------------------------------------
# Lead Flow
# ---------------------------------------------------------------------------

class TestLeadFlowIsolation:

    def test_lead_flow_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/lead_flows/",
                json={"name": "Flujo Privado Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            flow_id = resp_create.json()["id"]

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/lead_flows/", headers=api_b.headers)

        assert flow_id not in _ids(resp)

    def test_lead_flow_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/lead_flows/",
                json={"name": "Flujo Propio Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            flow_id = resp_create.json()["id"]
            resp = client.get("/lead_flows/", headers=api_a.headers)

        assert flow_id in _ids(resp)


# ---------------------------------------------------------------------------
# Lead Field Section
# ---------------------------------------------------------------------------

class TestLeadFieldSectionIsolation:

    def test_section_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/lead_field_sections/",
                json={"name": "Sección Privada Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            section_id = resp_create.json()["id"]

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/lead_field_sections/", headers=api_b.headers)

        assert section_id not in _ids(resp)

    def test_section_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/lead_field_sections/",
                json={"name": "Sección Propia Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            section_id = resp_create.json()["id"]
            resp = client.get("/lead_field_sections/", headers=api_a.headers)

        assert section_id in _ids(resp)


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------

class TestTagIsolation:

    def test_tag_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/tags/",
                json={"name": "Tag Privado Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            tag_id = resp_create.json()["id"]

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/tags/", headers=api_b.headers)

        assert tag_id not in _ids(resp)

    def test_tag_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/tags/",
                json={"name": "Tag Propio Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            tag_id = resp_create.json()["id"]
            resp = client.get("/tags/", headers=api_a.headers)

        assert tag_id in _ids(resp)


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class TestTeamIsolation:

    def test_team_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            team = api_a.create_team("Equipo Privado Alpha")

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/teams/", headers=api_b.headers)

        assert team["id"] not in _ids(resp)

    def test_team_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            team = api_a.create_team("Equipo Propio Alpha")
            resp = client.get("/teams/", headers=api_a.headers)

        assert team["id"] in _ids(resp)


# ---------------------------------------------------------------------------
# Nomenclator
# ---------------------------------------------------------------------------

class TestNomenclatorIsolation:

    def test_global_nomenclator_visible_to_all_orgs(self, client, ctx_alpha, ctx_beta):
        """Un nomenclador del admin org (global) debe ser visible para todas las organizaciones."""
        # El superadmin crea un nomenclador en la org admin (id=1 = ADMIN_ORG_ID)
        resp_create = client.post(
            "/nomenclators/",
            json={"name": "Nomenclador Global Test"},
            headers={"X-Organization-Id": str(ADMIN_ORG_ID)},
        )
        assert resp_create.status_code == 200
        nom_id = resp_create.json()["id"]

        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_a = client.get("/nomenclators/", headers=api_a.headers)

        with as_user(api_b, ctx_beta.owner):
            resp_b = client.get("/nomenclators/", headers=api_b.headers)

        assert nom_id in _ids(resp_a), "Alpha debe ver el nomenclador global"
        assert nom_id in _ids(resp_b), "Beta debe ver el nomenclador global"

    def test_org_nomenclator_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            resp_create = client.post(
                "/nomenclators/",
                json={"name": "Nomenclador Privado Alpha"},
                headers=api_a.headers,
            )
            assert resp_create.status_code == 200
            nom_id = resp_create.json()["id"]

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/nomenclators/", headers=api_b.headers)

        assert nom_id not in _ids(resp)


# ---------------------------------------------------------------------------
# Validation Rule
# ---------------------------------------------------------------------------

class TestValidationRuleIsolation:

    def test_validation_rule_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            # Necesitamos un campo para asociar la regla
            field = api_a.create_lead_field(
                campaign_id=ctx_alpha.campaign_id,
                name="Edad Regla",
                field_type_code="INT",
                section_id=ctx_alpha.section_id,
            )
            rule = api_a.create_rule(
                field_id=field["id"],
                name="Mayor de edad",
                expression="value >= 18",
                error_msg="Debe ser mayor de 18",
            )

        with as_user(api_b, ctx_beta.owner):
            resp = client.get("/validation_rules/", headers=api_b.headers)

        assert rule["id"] not in _ids(resp)


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------

class TestLeadIsolation:

    def test_leads_not_visible_from_other_org(self, client, ctx_alpha, ctx_beta):
        """Los leads de Alpha no deben aparecer cuando Beta consulta con el campaign_id de Alpha."""
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)

        with as_user(api_a, ctx_alpha.owner):
            field = api_a.create_lead_field(
                campaign_id=ctx_alpha.campaign_id,
                name="Nombre Lead",
                field_type_code="STRING",
                required=True,
                section_id=ctx_alpha.section_id,
            )
            lead = api_a.create_lead(
                campaign_id=ctx_alpha.campaign_id,
                values=[{"field_id": field["id"], "value": "Juan Alpha"}],
            )

        # Beta intenta listar los leads de la campaña de Alpha directamente
        with as_user(api_b, ctx_beta.owner):
            resp = client.get(
                f"/leads/?campaign_id={ctx_alpha.campaign_id}",
                headers=api_b.headers,
            )

        lead_ids = _ids(resp) if resp.status_code == 200 else []
        assert lead["id"] not in lead_ids, "Beta no debería ver los leads de Alpha"

    def test_leads_visible_from_own_org(self, client, ctx_alpha):
        api_a = ApiClient(client, ctx_alpha.org_id)

        with as_user(api_a, ctx_alpha.owner):
            field = api_a.create_lead_field(
                campaign_id=ctx_alpha.campaign_id,
                name="Nombre Lead Propio",
                field_type_code="STRING",
                required=True,
                section_id=ctx_alpha.section_id,
            )
            lead = api_a.create_lead(
                campaign_id=ctx_alpha.campaign_id,
                values=[{"field_id": field["id"], "value": "Maria Alpha"}],
            )
            resp = client.get(
                f"/leads/?campaign_id={ctx_alpha.campaign_id}",
                headers=api_a.headers,
            )

        assert lead["id"] in _ids(resp)


# ---------------------------------------------------------------------------
# Multi-org user
# ---------------------------------------------------------------------------

class TestMultiOrgUser:

    def test_member_multi_sees_alpha_data_with_alpha_header(
        self, client, ctx_alpha, ctx_beta, member_multi
    ):
        """Un usuario en ambas orgs ve los datos de cada una según el header."""
        api_a = ApiClient(client, ctx_alpha.org_id)
        api_b = ApiClient(client, ctx_beta.org_id)
        api_m_a = ApiClient(client, ctx_alpha.org_id)
        api_m_b = ApiClient(client, ctx_beta.org_id)

        # Alpha crea un equipo
        with as_user(api_a, ctx_alpha.owner):
            team_a = api_a.create_team("Equipo Alpha Multi")

        # Beta crea un equipo
        with as_user(api_b, ctx_beta.owner):
            team_b = api_b.create_team("Equipo Beta Multi")

        # member_multi con contexto Alpha ve el equipo de Alpha, no el de Beta
        with as_user(api_m_a, member_multi):
            resp_a = client.get("/teams/", headers=api_m_a.headers)

        # member_multi con contexto Beta ve el equipo de Beta, no el de Alpha
        with as_user(api_m_b, member_multi):
            resp_b = client.get("/teams/", headers=api_m_b.headers)

        ids_as_alpha = _ids(resp_a)
        ids_as_beta = _ids(resp_b)

        assert team_a["id"] in ids_as_alpha
        assert team_b["id"] not in ids_as_alpha

        assert team_b["id"] in ids_as_beta
        assert team_a["id"] not in ids_as_beta
