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
from app.models.lead_field import LeadField
from app.models.lead_field_section import LeadFieldSection
from app.models.campaign import Campaign


def _resolve_internal_id(db_session, model, public_uuid_or_int):
    """Ídem tests/functional/test_leads.py::_resolve_internal_id -- initial_structure
    devuelve public_uuid (Fase 3) pero LeadField necesita el id interno."""
    if isinstance(public_uuid_or_int, int):
        return public_uuid_or_int
    return db_session.query(model.id).filter_by(public_uuid=public_uuid_or_int).scalar()


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
        # nom/item son filas ORM crudas (construidas directo en la DB); "id" en la respuesta
        # de la API es el public_uuid (Fase 3, ver backend/AGENTS.md §18), no el id interno.
        assert any(n["id"] == nom.public_uuid for n in resp_nom.json()["nomenclators"])

        resp_item = api.client.get("/search", params={"query": "Valor Búsqueda Test"}, headers=api.headers)
        assert resp_item.status_code == 200, resp_item.text
        assert any(i["id"] == item.public_uuid for i in resp_item.json()["nomenclator_items"])

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

    def test_search_leads_only_matches_title_fields(self, api, db_session, initial_structure):
        """
        El buscador global (GET /search, usado por el navbar) debía buscar en
        cualquier campo STRING/SELECTOR del lead -- mismo problema que ya se había
        corregido para POST /leads/search (ver test_leads.py::
        test_search_leads_text_query_ignores_non_title_field, fix 2026-08-15).
        Se acota acá también a los campos que arman el título del lead
        (LeadField.title_order IS NOT NULL), pedido del usuario para el buscador
        del navbar.
        """
        camp_id = initial_structure["campaign_id"]
        org_id = initial_structure["org_id"]
        section_id = initial_structure["section_id"]
        camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
        section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

        f_nombre = LeadField(
            name="Nombre", field_type_code="STRING", campaign_id=camp_internal_id,
            order=1, lead_field_section_id=section_internal_id, organization_id=org_id,
            active=True, title_order=1,
        )
        f_nota = LeadField(
            name="Nota interna", field_type_code="STRING", campaign_id=camp_internal_id,
            order=2, lead_field_section_id=section_internal_id, organization_id=org_id,
            active=True,  # sin title_order
        )
        db_session.add_all([f_nombre, f_nota])
        db_session.commit()

        api.create_lead(campaign_id=camp_id, values=[
            {"field_id": f_nombre.id, "value": "Carla Ferreyra Buscada Qwe"},
        ])
        api.create_lead(campaign_id=camp_id, values=[
            {"field_id": f_nota.id, "value": "Llamar de nuevo Buscada Qwe"},
        ])

        # Matchea el lead cuyo campo título contiene el texto
        resp_titulo = api.client.get("/search", params={"query": "Buscada Qwe"}, headers=api.headers)
        assert resp_titulo.status_code == 200, resp_titulo.text
        leads_encontrados = resp_titulo.json()["leads"]
        assert len(leads_encontrados) == 1
        nombre_val = next(v for v in leads_encontrados[0]["field_values"] if v["field_id"] == f_nombre.id)
        assert nombre_val["value"] == "Carla Ferreyra Buscada Qwe"
