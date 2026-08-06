"""
test_lead_comment_and_view_permissions.py
==========================================
Regresión de los bugs encontrados en el audit de get_by_id() de esta sesión
(ver backend/AGENTS.md §18-ter): `LeadCommentService._assert_can_modify_comment`
y `LeadViewService._can_modify` leían `.created_by` sobre el resultado de
`repository.get_by_id()`, que en realidad es el schema Pydantic (no el ORM
crudo) y no tiene ese campo desde que se sacó de `BaseDetailedResponse` a favor
de `creator`/`updater` -- tiraba `AttributeError` en CUALQUIER intento de editar
o borrar un comentario/vista hecho por alguien que no fuera superuser/owner.

Se corrigió comparando contra `.creator.id` (uuid real) en vez de `.created_by`
(id interno, ya no existe). Estos tests no existían todavía para estas dos
entidades -- `test_campaign.py` ya tenía cobertura equivalente (hallazgo #19)
para Campaign, que sirvió de plantilla acá.
"""
import pytest
from tests.fixtures.user_fixtures import _make_user, _link_user_to_org, as_user


@pytest.fixture
def two_users(db_session, initial_structure):
    """Dos usuarios regulares (no superadmin) vinculados a la organización de prueba."""
    org_id = initial_structure["org_id"]
    creator  = _make_user(db_session, "Perm Creator",  f"perm_creator_{org_id}@test.com")
    outsider = _make_user(db_session, "Perm Outsider", f"perm_outsider_{org_id}@test.com")
    _link_user_to_org(db_session, creator,  org_id)
    _link_user_to_org(db_session, outsider, org_id)
    db_session.commit()
    return {"creator": creator, "outsider": outsider, "org_id": org_id}


# ======================================================================
# LeadComment — control de acceso en update / delete
# ======================================================================

def _create_comment_lead(api, campaign_id):
    field = api.create_lead_field(campaign_id, "Campo Comentario Perm", "STRING")
    return api.create_lead(campaign_id, [{"field_id": field["id"], "value": "x"}])


def test_comment_update_by_creator_succeeds(api, initial_structure, two_users):
    """El usuario que creó el comentario puede editarlo."""
    camp_id = initial_structure["campaign_id"]
    creator = two_users["creator"]

    with as_user(api, creator):
        lead = _create_comment_lead(api, camp_id)
        resp_create = api.client.post(
            "/lead_comments/", json={"lead_id": lead["id"], "content": "Original"}, headers=api.headers,
        )
        assert resp_create.status_code in (200, 201), resp_create.text
        comment_id = resp_create.json()["id"]

        resp = api.client.put(
            f"/lead_comments/{comment_id}", json={"content": "Editado por creador"}, headers=api.headers,
        )

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"
    assert resp.json()["content"] == "Editado por creador"


def test_comment_update_by_non_creator_fails_with_403(api, initial_structure, two_users):
    """Un usuario que no creó el comentario debe recibir 403 al intentar editarlo."""
    camp_id  = initial_structure["campaign_id"]
    creator  = two_users["creator"]
    outsider = two_users["outsider"]

    with as_user(api, creator):
        lead = _create_comment_lead(api, camp_id)
        resp_create = api.client.post(
            "/lead_comments/", json={"lead_id": lead["id"], "content": "Protegido"}, headers=api.headers,
        )
        assert resp_create.status_code in (200, 201), resp_create.text
        comment_id = resp_create.json()["id"]

    with as_user(api, outsider):
        resp = api.client.put(
            f"/lead_comments/{comment_id}", json={"content": "Intento ajeno"}, headers=api.headers,
        )

    assert resp.status_code == 403, f"Esperaba 403 pero recibió {resp.status_code}: {resp.text}"


def test_comment_delete_by_creator_succeeds(api, initial_structure, two_users):
    """El usuario que creó el comentario puede borrarlo."""
    camp_id = initial_structure["campaign_id"]
    creator = two_users["creator"]

    with as_user(api, creator):
        lead = _create_comment_lead(api, camp_id)
        resp_create = api.client.post(
            "/lead_comments/", json={"lead_id": lead["id"], "content": "Borrable"}, headers=api.headers,
        )
        assert resp_create.status_code in (200, 201), resp_create.text
        comment_id = resp_create.json()["id"]

        resp = api.client.delete(f"/lead_comments/{comment_id}", headers=api.headers)

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"


def test_comment_delete_by_non_creator_fails_with_403(api, initial_structure, two_users):
    """Un usuario que no creó el comentario debe recibir 403 al intentar borrarlo."""
    camp_id  = initial_structure["campaign_id"]
    creator  = two_users["creator"]
    outsider = two_users["outsider"]

    with as_user(api, creator):
        lead = _create_comment_lead(api, camp_id)
        resp_create = api.client.post(
            "/lead_comments/", json={"lead_id": lead["id"], "content": "Protegido Delete"}, headers=api.headers,
        )
        assert resp_create.status_code in (200, 201), resp_create.text
        comment_id = resp_create.json()["id"]

    with as_user(api, outsider):
        resp = api.client.delete(f"/lead_comments/{comment_id}", headers=api.headers)

    assert resp.status_code == 403, f"Esperaba 403 pero recibió {resp.status_code}: {resp.text}"


def test_comment_update_by_superuser_succeeds_regardless_of_creator(api, db_session, initial_structure):
    """Un superuser puede editar cualquier comentario aunque no lo haya creado."""
    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]
    author    = _make_user(db_session, "Comment Author", f"comment_author_{org_id}@test.com")
    superuser = _make_user(db_session, "Comment Super",  f"comment_super_{org_id}@test.com", is_superuser=True)
    _link_user_to_org(db_session, author,    org_id)
    _link_user_to_org(db_session, superuser, org_id)
    db_session.commit()

    with as_user(api, author):
        lead = _create_comment_lead(api, camp_id)
        resp_create = api.client.post(
            "/lead_comments/", json={"lead_id": lead["id"], "content": "De otro"}, headers=api.headers,
        )
        assert resp_create.status_code in (200, 201), resp_create.text
        comment_id = resp_create.json()["id"]

    with as_user(api, superuser):
        resp = api.client.put(
            f"/lead_comments/{comment_id}", json={"content": "Editado por superuser"}, headers=api.headers,
        )

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"


# ======================================================================
# LeadView — control de acceso en update / delete
# ======================================================================

def _create_private_view(api, campaign_id, name):
    resp = api.client.post(
        "/lead_views/", json={"name": name, "campaign_id": campaign_id, "visibility": "PRIVATE"},
        headers=api.headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _create_public_view(api, campaign_id, name):
    resp = api.client.post(
        "/lead_views/", json={"name": name, "campaign_id": campaign_id, "visibility": "PUBLIC"},
        headers=api.headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_view_update_by_creator_succeeds(api, initial_structure, two_users):
    """El usuario que creó la vista puede editarla."""
    camp_id = initial_structure["campaign_id"]
    creator = two_users["creator"]

    with as_user(api, creator):
        view = _create_private_view(api, camp_id, "Vista Editable Creador")
        resp = api.client.put(
            f"/lead_views/{view['id']}", json={"name": "Vista Renombrada"}, headers=api.headers,
        )

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"
    assert resp.json()["name"] == "Vista Renombrada"


def test_view_update_by_non_creator_fails_with_403(api, initial_structure, two_users):
    """Un usuario que puede VER la vista (PUBLIC) pero no la creó debe recibir 403 al
    intentar editarla. Nota: con visibility=PRIVATE esto es imposible de probar -- el
    filtro de seguridad de LeadViewRepository.apply_security_filter excluye las vistas
    PRIVATE ajenas directo en el get_by_id() previo al chequeo de permisos, así que un
    outsider recibe 404 (ni siquiera "existe" para él) antes de llegar al chequeo de
    "¿sos el creador?" que este test quiere ejercitar -- bug real de test encontrado
    2026-08-01, ver backend/AGENTS.md."""
    camp_id  = initial_structure["campaign_id"]
    creator  = two_users["creator"]
    outsider = two_users["outsider"]

    with as_user(api, creator):
        view = _create_public_view(api, camp_id, "Vista Protegida")

    with as_user(api, outsider):
        resp = api.client.put(
            f"/lead_views/{view['id']}", json={"name": "Intento ajeno"}, headers=api.headers,
        )

    assert resp.status_code == 403, f"Esperaba 403 pero recibió {resp.status_code}: {resp.text}"


def test_view_delete_by_creator_succeeds(api, initial_structure, two_users):
    """El usuario que creó la vista puede borrarla."""
    camp_id = initial_structure["campaign_id"]
    creator = two_users["creator"]

    with as_user(api, creator):
        view = _create_private_view(api, camp_id, "Vista Borrable Creador")
        resp = api.client.delete(f"/lead_views/{view['id']}", headers=api.headers)

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"


def test_view_delete_by_non_creator_fails_with_403(api, initial_structure, two_users):
    """Un usuario que puede VER la vista (PUBLIC) pero no la creó debe recibir 403 al
    intentar borrarla. Mismo motivo que el test de update: con PRIVATE el outsider ni
    siquiera puede resolver el get_by_id() previo (filtro de seguridad), así que da 404
    en vez de 403 -- ver comentario en test_view_update_by_non_creator_fails_with_403."""
    camp_id  = initial_structure["campaign_id"]
    creator  = two_users["creator"]
    outsider = two_users["outsider"]

    with as_user(api, creator):
        view = _create_public_view(api, camp_id, "Vista Protegida Delete")

    with as_user(api, outsider):
        resp = api.client.delete(f"/lead_views/{view['id']}", headers=api.headers)

    assert resp.status_code == 403, f"Esperaba 403 pero recibió {resp.status_code}: {resp.text}"


def test_view_update_by_superuser_succeeds_regardless_of_creator(api, db_session, initial_structure):
    """Un superuser puede editar cualquier vista aunque no la haya creado."""
    camp_id = initial_structure["campaign_id"]
    org_id  = initial_structure["org_id"]
    author    = _make_user(db_session, "View Author", f"view_author_{org_id}@test.com")
    superuser = _make_user(db_session, "View Super",  f"view_super_{org_id}@test.com", is_superuser=True)
    _link_user_to_org(db_session, author,    org_id)
    _link_user_to_org(db_session, superuser, org_id)
    db_session.commit()

    with as_user(api, author):
        view = _create_private_view(api, camp_id, "Vista De Otro")

    with as_user(api, superuser):
        resp = api.client.put(
            f"/lead_views/{view['id']}", json={"name": "Editada por superuser"}, headers=api.headers,
        )

    assert resp.status_code == 200, f"Esperaba 200 pero recibió {resp.status_code}: {resp.text}"
