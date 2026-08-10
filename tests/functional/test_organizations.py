"""
test_organizations.py
======================
Hallazgo #15 (ronda de bug-hunting, 2026-07-10 investigado / 2026-07-11 resuelto):
PUT/DELETE/activar-desactivar de `Organization` (individual y bulk) validaban el
PERMISO contra la organización del header `X-Organization-Id`, pero el ACCESO al
objeto (gatekeeper de `get_by_id`, vía `OrganizationRepository.apply_security_filter`)
contra "cualquier organización de la que el usuario sea miembro" — sin exigir que
coincida con el header. Un usuario miembro de dos o más organizaciones podía editar
la organización donde tiene un rol menor, mandando el header de la organización
donde sí tiene el permiso `organization:update`.

También cubre un hallazgo relacionado, encontrado durante la implementación de #15:
`BaseRepository.bulk_delete` no chequeaba `delete_strategy == PROTECTED` antes de
hacer hard-delete (a diferencia del `delete()` individual, que sí lo bloquea). El
único caso alcanzable por HTTP es `POST /organizations/bulk-delete`, porque
`Organization` es la única de las 7 entidades `PROTECTED` cuyo controller expone
`DELETE` (las otras 6 son `READ_ONLY`).

Ver hallazgos_agente/organizaciones.md y docs/organizaciones.md §3.
"""
import pytest

from tests.fixtures.user_fixtures import _link_user_to_org, _make_user, as_user
from tests.helpers.api_helpers import ApiClient


@pytest.fixture
def cross_org_user(db_session, ctx_alpha, ctx_beta):
    """Usuario admin en Alpha (SÍ tiene organization:update ahí) y viewer en Beta
    (NO tiene ese permiso) — el escenario exacto del hallazgo #15."""
    user = _make_user(db_session, "Cross Org", "cross_org_15@test.com")
    _link_user_to_org(db_session, user, ctx_alpha.org_id, is_owner=False, role_code="admin")
    _link_user_to_org(db_session, user, ctx_beta.org_id, is_owner=False, role_code="viewer")
    db_session.commit()
    return user


class TestOrganizationHeaderVsAccessMismatch:
    def test_cannot_update_other_org_using_header_of_own_org(
        self, client, db_session, ctx_alpha, ctx_beta, cross_org_user
    ):
        """El ataque descripto en el hallazgo: header = Alpha (donde tiene permiso),
        obj_id en la URL = Beta (donde NO tiene permiso, pero SÍ es miembro)."""
        api = ApiClient(client, ctx_alpha.org_id)
        with as_user(api, cross_org_user, db_session):
            resp = api.client.put(
                f"/organizations/{ctx_beta.org_uuid}",
                json={"name": "Beta Hackeada"},
                headers=api.headers,
            )
        assert resp.status_code == 403

    def test_can_update_own_org_with_matching_header(
        self, client, db_session, ctx_alpha, cross_org_user
    ):
        """Contraparte positiva: header y obj_id apuntan a la misma org donde
        el usuario sí tiene permiso → debe funcionar normalmente."""
        api = ApiClient(client, ctx_alpha.org_id)
        with as_user(api, cross_org_user, db_session):
            resp = api.client.put(
                f"/organizations/{ctx_alpha.org_uuid}",
                json={"name": "Alpha Renombrada"},
                headers=api.headers,
            )
        assert resp.status_code == 200, resp.text

    def test_superadmin_bypasses_active_org_check(self, client, db_session, ctx_alpha, ctx_beta):
        """El superadmin no tiene esta restricción — igual que ya pasaba en
        apply_security_filter antes del fix."""
        superadmin = _make_user(db_session, "Super Cross", "super_cross_15@test.com", is_superuser=True)
        db_session.commit()

        api = ApiClient(client, ctx_alpha.org_id)
        with as_user(api, superadmin, db_session):
            resp = api.client.put(
                f"/organizations/{ctx_beta.org_uuid}",
                json={"name": "Beta vía superadmin"},
                headers=api.headers,
            )
        assert resp.status_code == 200, resp.text

    def test_bulk_active_skips_ids_outside_active_org(
        self, client, db_session, ctx_alpha, ctx_beta, cross_org_user
    ):
        """El mismo criterio aplicado a POST /organizations/bulk-active: el id de
        Beta debe quedar en 'failed', no colarse en 'activated'."""
        api = ApiClient(client, ctx_alpha.org_id)
        with as_user(api, cross_org_user, db_session):
            resp = api.client.post(
                "/organizations/bulk-active",
                json={"ids": [ctx_alpha.org_uuid, ctx_beta.org_uuid]},
                headers=api.headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert ctx_beta.org_uuid not in body.get("activated", [])
        assert ctx_beta.org_uuid not in body.get("already_active", [])
        assert ctx_beta.org_uuid in body["failed"]


class TestOrganizationBulkDeleteRespectsProtected:
    def test_bulk_delete_never_removes_organizations(self, client, ctx_alpha):
        """Hallazgo relacionado: bulk-delete no debe poder bypasear PROTECTED,
        a diferencia de cómo se comportaba antes del fix en base_repository.py."""
        api = ApiClient(client, ctx_alpha.org_id)  # client fixture actúa como superadmin
        resp = api.client.post(
            "/organizations/bulk-delete",
            json={"ids": [ctx_alpha.org_uuid]},
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert ctx_alpha.org_uuid in body["failed"]
        assert ctx_alpha.org_uuid not in body["deleted"]

        # La organización debe seguir existiendo (esto es seguro de verificar acá:
        # bulk_delete no lanza excepción, solo devuelve un resultado, así que no
        # pisa la limitación de db_session documentada en AGENTS.md §5.1).
        resp_check = api.client.get(f"/organizations/{ctx_alpha.org_uuid}", headers=api.headers)
        assert resp_check.status_code == 200
