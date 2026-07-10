"""
test_promote_to_org_owner.py
==============================
Cobertura del hallazgo #6 de la auditoría (2026-07-10): la ruta
`PATCH /users/organization/{organization_id}/promote-owner/{user_id}` tenía
`dependencies=[Depends(require_superuser)]`, que corta con 403 a cualquier
usuario no-superadmin ANTES de que el service llegue a ejecutarse.

`UserService.promote_to_org_owner` tiene, desde siempre, una segunda rama de
autorización: "SOLO un Super Admin o un Owner actual de ESA organización
puede hacerlo" — pero esa rama (`elif user_context.is_owner: ...`) era código
muerto, inalcanzable, porque `require_superuser` ya había bloqueado a
cualquier no-superadmin antes.

Fix: se sacó `Depends(require_superuser)` de la ruta. Queda solo
`user_context=Depends(get_current_user_roles)` (autenticación); la
autorización fina (superadmin O owner-de-esa-org) la maneja el service, que
ya la tenía bien implementada.

Ver hallazgos_agente/usuarios_y_permisos.md para el detalle completo.
"""
from app.models.security_models import UserOrganization
from tests.fixtures.user_fixtures import (
    _apply_user_overrides,
    _link_user_to_org,
    _make_user,
    _remove_user_overrides,
)


class TestPromoteToOrgOwner:
    def test_owner_can_promote_member_in_own_org(self, client, db_session, initial_structure):
        """La rama antes inalcanzable: un owner (no superadmin) SÍ debe poder
        promover a otro miembro de su propia organización."""
        from app.main import app

        org_id = initial_structure["org_id"]
        owner_user = _make_user(db_session, "Owner Promotor", "owner_promotor@test.com")
        _link_user_to_org(db_session, owner_user, org_id, is_owner=True, role_code="admin")
        target_user = _make_user(db_session, "Miembro A Promover", "miembro_promover@test.com")
        _link_user_to_org(db_session, target_user, org_id, is_owner=False, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, owner_user, org_id, is_owner=True)
        try:
            resp = client.patch(
                f"/users/organization/{org_id}/promote-owner/{target_user.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200, resp.text
        finally:
            _remove_user_overrides(app)

        link = db_session.query(UserOrganization).filter_by(
            user_id=target_user.id, organization_id=org_id
        ).first()
        assert link is not None
        assert link.is_owner is True

    def test_owner_can_promote_user_not_yet_member_of_org(self, client, db_session, initial_structure):
        """Si el usuario destino no tenía membresía en la org, se le crea una
        directamente con is_owner=True — vía el path de owner, no solo superadmin."""
        from app.main import app

        org_id = initial_structure["org_id"]
        owner_user = _make_user(db_session, "Owner Promotor 2", "owner_promotor2@test.com")
        _link_user_to_org(db_session, owner_user, org_id, is_owner=True, role_code="admin")
        outsider = _make_user(db_session, "Usuario Sin Org", "sin_org@test.com")
        db_session.commit()

        _apply_user_overrides(app, owner_user, org_id, is_owner=True)
        try:
            resp = client.patch(
                f"/users/organization/{org_id}/promote-owner/{outsider.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200, resp.text
        finally:
            _remove_user_overrides(app)

        link = db_session.query(UserOrganization).filter_by(
            user_id=outsider.id, organization_id=org_id
        ).first()
        assert link is not None
        assert link.is_owner is True

    def test_owner_cannot_promote_in_a_different_org(self, client, db_session, initial_structure):
        """Un owner de la org A no puede usar ese poder para promover a alguien
        en la org B, aunque conozca su user_id."""
        from app.main import app

        org_a = initial_structure["org_id"]
        owner_user = _make_user(db_session, "Owner Org A", "owner_org_a@test.com")
        _link_user_to_org(db_session, owner_user, org_a, is_owner=True, role_code="admin")

        # Creamos una segunda organización "a mano" para no depender de otro fixture.
        from app.models.organization import Organization
        org_b = Organization(name="Org B Ajena")
        db_session.add(org_b)
        db_session.flush()
        target_user = _make_user(db_session, "Miembro Org B", "miembro_org_b@test.com")
        _link_user_to_org(db_session, target_user, org_b.id, is_owner=False, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, owner_user, org_a, is_owner=True)
        try:
            resp = client.patch(
                f"/users/organization/{org_b.id}/promote-owner/{target_user.id}",
                headers={"X-Organization-Id": str(org_a)},  # header = su propia org, no la B
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_regular_member_cannot_promote_anyone(self, client, db_session, initial_structure):
        """Ni superadmin ni owner: debe recibir 403 con el mensaje del service."""
        from app.main import app

        org_id = initial_structure["org_id"]
        regular_user = _make_user(db_session, "Miembro Comun", "miembro_comun@test.com")
        _link_user_to_org(db_session, regular_user, org_id, is_owner=False, role_code="agent")
        target_user = _make_user(db_session, "Otro Miembro", "otro_miembro@test.com")
        _link_user_to_org(db_session, target_user, org_id, is_owner=False, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, regular_user, org_id, is_owner=False)
        try:
            resp = client.patch(
                f"/users/organization/{org_id}/promote-owner/{target_user.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
            assert "permisos" in resp.text.lower()
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_still_promote(self, api, db_session, initial_structure):
        """Control: el superadmin sigue pudiendo promover, como antes del fix."""
        org_id = initial_structure["org_id"]
        target_user = _make_user(db_session, "Miembro Para Superadmin", "miembro_superadmin@test.com")
        _link_user_to_org(db_session, target_user, org_id, is_owner=False, role_code="agent")
        db_session.commit()

        resp = api.client.patch(
            f"/users/organization/{org_id}/promote-owner/{target_user.id}",
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text

        link = db_session.query(UserOrganization).filter_by(
            user_id=target_user.id, organization_id=org_id
        ).first()
        assert link.is_owner is True
