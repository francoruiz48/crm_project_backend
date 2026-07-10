"""
test_global_search.py
=======================
Cobertura del hallazgo #8 de la auditoría (2026-07-10): `SearchService.global_search`
pasaba `search_fields=["code", "value"]` para `NomenclatorItem`, pero el modelo no
tiene columna `code` (solo `value`). No rompía nada — `BaseRepository.get_all` ignora
en silencio los campos que no existen (`hasattr(cls.model, field)`) — pero era código
que aparentaba buscar por dos campos cuando en realidad solo buscaba por uno. Se quitó
`"code"` de la lista. Ver docs/busqueda.md §4 y hallazgos_agente/busqueda.md.

No existía tampoco ningún test para `GET /search` (ni el caso feliz, ni la validación
de longitud mínima, ni el aislamiento de tenant) — se aprovecha este fix para agregar
la cobertura básica que faltaba.
"""
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem


def _create_nomenclator_with_item(db_session, org_id, nom_name, item_value):
    nom = Nomenclator(name=nom_name, organization_id=org_id)
    db_session.add(nom)
    db_session.flush()
    item = NomenclatorItem(nomenclator_id=nom.id, value=item_value, organization_id=org_id)
    db_session.add(item)
    db_session.commit()
    return nom, item


class TestGlobalSearch:
    def test_search_requires_minimum_query_length(self, api):
        resp = api.client.get("/search", params={"query": "ab"}, headers=api.headers)
        assert resp.status_code == 422

    def test_search_finds_campaign_by_name(self, api, initial_structure):
        campaign = api.create_campaign(
            workspace_id=initial_structure["workspace_id"],
            name="Campaña Búsqueda Única XYZ",
            lead_flow_id=initial_structure["lead_flow_id"],
        )
        resp = api.client.get("/search", params={"query": "Búsqueda Única XYZ"}, headers=api.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert any(c["id"] == campaign["id"] for c in body["campaigns"])

    def test_search_finds_workspace_by_name(self, api):
        ws = api.create_workspace(name="Workspace Búsqueda Rara ABC")
        resp = api.client.get("/search", params={"query": "Búsqueda Rara ABC"}, headers=api.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert any(w["id"] == ws["id"] for w in body["workspaces"])

    def test_search_finds_nomenclator_by_name_and_item_by_value(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        nom, item = _create_nomenclator_with_item(
            db_session, org_id, "Catálogo Búsqueda Test", "Valor Búsqueda Test"
        )

        resp_nom = api.client.get("/search", params={"query": "Catálogo Búsqueda Test"}, headers=api.headers)
        assert resp_nom.status_code == 200, resp_nom.text
        assert any(n["id"] == nom.id for n in resp_nom.json()["nomenclators"])

        resp_item = api.client.get("/search", params={"query": "Valor Búsqueda Test"}, headers=api.headers)
        assert resp_item.status_code == 200, resp_item.text
        assert any(i["id"] == item.id for i in resp_item.json()["nomenclator_items"])

    def test_search_respects_tenant_isolation(self, api, db_session, initial_structure):
        """Un item de nomenclador de OTRA organización no debe aparecer en la
        búsqueda global de la organización activa."""
        from app.models.organization import Organization

        other_org = Organization(name="Org Ajena Búsqueda")
        db_session.add(other_org)
        db_session.flush()
        _create_nomenclator_with_item(
            db_session, other_org.id, "Catálogo De Otra Org Zzq", "Valor De Otra Org Zzq"
        )
        db_session.commit()

        resp = api.client.get("/search", params={"query": "De Otra Org Zzq"}, headers=api.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["nomenclators"] == []
        assert body["nomenclator_items"] == []
