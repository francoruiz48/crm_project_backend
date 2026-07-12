"""
test_nomenclators.py
=====================
Cobertura de la protección de nomencladores/items "globales" (organization_id=ADMIN_ORG_ID).

Bug corregido (2026-07-10): NomenclatorItemService comparaba `organization_id` contra
`None` para decidir si un ítem pertenecía a un catálogo global, pero esa columna es
NOT NULL en el modelo — los catálogos globales reales viven bajo ADMIN_ORG_ID (ver
app/db/init_data.py::get_or_create_nomenclator). La condición nunca se cumplía, así que
la protección "solo un SuperAdmin puede tocar catálogos globales" nunca se activaba: un
admin de cualquier organización podía crear, editar o borrar ítems de un catálogo
compartido entre todas las organizaciones.
"""
import pytest
from app.core.constans import ADMIN_ORG_ID
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from tests.fixtures.user_fixtures import (
    _apply_user_overrides,
    _link_user_to_org,
    _make_user,
    _remove_user_overrides,
)


@pytest.fixture
def global_nomenclator(db_session):
    """Nomenclador 'global': sembrado bajo la organización admin (ADMIN_ORG_ID)."""
    nom = Nomenclator(name="Catálogo Global Test", organization_id=ADMIN_ORG_ID)
    db_session.add(nom)
    db_session.flush()
    item = NomenclatorItem(nomenclator_id=nom.id, value="Opción Global", organization_id=ADMIN_ORG_ID)
    db_session.add(item)
    db_session.commit()
    return nom, item


class TestGlobalNomenclatorProtection:
    def test_admin_cannot_create_item_in_global_nomenclator(self, client, db_session, initial_structure, global_nomenclator):
        """Un admin de organización (no superadmin) NO puede agregar items a un nomenclador global."""
        from app.main import app

        nom, _ = global_nomenclator
        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Org Admin", "org_admin_nom@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.post(
                "/nomenclator_items/",
                json={"value": "Intento no autorizado", "nomenclator_id": nom.id},
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_admin_cannot_update_item_in_global_nomenclator(self, client, db_session, initial_structure, global_nomenclator):
        """Un admin de organización NO puede editar un item de un nomenclador global."""
        from app.main import app

        _, item = global_nomenclator
        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Org Admin Update", "org_admin_nom_upd@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.put(
                f"/nomenclator_items/{item.id}",
                json={"value": "Valor Modificado"},
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_admin_cannot_delete_item_in_global_nomenclator(self, client, db_session, initial_structure, global_nomenclator):
        """Un admin de organización NO puede borrar un item de un nomenclador global."""
        from app.main import app

        _, item = global_nomenclator
        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Org Admin Delete", "org_admin_nom_del@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.delete(
                f"/nomenclator_items/{item.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_create_item_in_global_nomenclator(self, client, initial_structure, global_nomenclator):
        """El SuperAdmin sí puede agregar items a un nomenclador global, y el item nuevo
        hereda organization_id=ADMIN_ORG_ID (REGLA A: antes de este fix, forzaba
        organization_id=None, lo cual habría violado la constraint NOT NULL de la columna)."""
        nom, _ = global_nomenclator
        org_id = initial_structure["org_id"]

        # El fixture `client` ya actúa como superadmin por default (ver tests/fixtures/client.py).
        resp = client.post(
            "/nomenclator_items/",
            json={"value": "Opción Nueva Global", "nomenclator_id": nom.id},
            headers={"X-Organization-Id": str(org_id)},
        )
        assert resp.status_code == 200
        assert resp.json()["organization_id"] == ADMIN_ORG_ID

    def test_superadmin_can_update_and_delete_item_in_global_nomenclator(self, client, initial_structure, global_nomenclator):
        """El SuperAdmin sí puede editar y borrar items de un nomenclador global.

        Importante: la escritura (a diferencia de la lectura) SOLO toca filas de la
        organización activa en el request (`_apply_tenant_filter(is_read_operation=False)`,
        ver convenciones_generales.md §6) — nunca las de ADMIN_ORG_ID, ni siquiera para un
        superadmin. Para editar/borrar un ítem de un nomenclador global hay que operar
        "parado en" la organización Panel Global (X-Organization-Id=ADMIN_ORG_ID), no en
        cualquier otra organización. Por eso acá se manda ese header y no el de
        `initial_structure`.
        """
        _, item = global_nomenclator

        resp_update = client.put(
            f"/nomenclator_items/{item.id}",
            json={"value": "Valor Editado Por Superadmin"},
            headers={"X-Organization-Id": str(ADMIN_ORG_ID)},
        )
        assert resp_update.status_code == 200

        resp_delete = client.delete(
            f"/nomenclator_items/{item.id}",
            headers={"X-Organization-Id": str(ADMIN_ORG_ID)},
        )
        assert resp_delete.status_code == 200

    def test_admin_can_manage_items_in_own_org_nomenclator(self, client, db_session, initial_structure):
        """Control: un admin de organización SÍ puede crear items en un nomenclador
        de su PROPIA organización (no global) — confirma que el fix no sobre-restringe."""
        from app.main import app

        org_id = initial_structure["org_id"]
        nom = Nomenclator(name="Catálogo Propio", organization_id=org_id)
        db_session.add(nom)
        db_session.flush()
        db_session.commit()

        admin_user = _make_user(db_session, "Org Admin Own", "org_admin_nom_own@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.post(
                "/nomenclator_items/",
                json={"value": "Item Propio", "nomenclator_id": nom.id},
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            # Un item de un nomenclador NO global no debe heredar ADMIN_ORG_ID.
            assert resp.json()["organization_id"] == org_id
        finally:
            _remove_user_overrides(app)
