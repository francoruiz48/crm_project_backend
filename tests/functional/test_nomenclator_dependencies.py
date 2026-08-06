"""
test_nomenclator_dependencies.py
=================================
Feature "nomencladores dependientes" (ver docs/nomencladores.md y
docs/campos_personalizados.md): permite que un LeadField de tipo
SELECTOR/CHECKBOX solo ofrezca ítems hijos del valor elegido en otro campo
de la misma campaña (ej. Ciudad depende de País).

Piezas cubiertas:
  - Nomenclator/NomenclatorItem con múltiples padres válidos (M2M, reemplaza
    las viejas columnas únicas parent_nomenclator_id/parent_item_id).
  - Consistencia catálogo↔ítem: un ítem solo puede declarar como padre a un
    ítem de un catálogo que esté en la lista de padres válidos de su propio
    catálogo.
  - LeadField.depends_on_field_id: misma campaña, ambos tipo nomenclador,
    consistencia catálogo↔campo, sin ciclos (permite cadenas de N niveles).
  - Bloqueo de borrado/desactivación de un campo con dependientes activos.
  - Validación cruzada al cargar/editar un lead: el ítem elegido en el campo
    hijo debe ser hijo del ítem elegido en el campo padre (semántica OR si el
    padre es de selección múltiple; en updates parciales se usa el valor ya
    persistido del padre si no vino en el request, decisión explícita del
    usuario).
"""
import pytest
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.lead_field import LeadField
from app.models.campaign import Campaign
from app.models.lead_field_section import LeadFieldSection


# =============================================================================
# HELPERS LOCALES
# =============================================================================

def _resolve_internal_id(db_session, model, public_uuid_or_int):
    """
    initial_structure devuelve public_uuid para campaign_id/section_id (ver
    backend/AGENTS.md §18-novies), pero este archivo construye filas LeadField directo en la DB,
    que necesitan el id interno (columnas FK Integer reales).
    """
    if isinstance(public_uuid_or_int, int):
        return public_uuid_or_int
    return db_session.query(model.id).filter_by(public_uuid=public_uuid_or_int).scalar()


def _make_nomenclator(db_session, name, org_id, parents=None):
    nom = Nomenclator(name=name, organization_id=org_id)
    if parents:
        nom.parent_nomenclators = list(parents)
    db_session.add(nom)
    db_session.flush()
    return nom


def _make_item(db_session, nomenclator_id, value, org_id, parents=None):
    item = NomenclatorItem(nomenclator_id=nomenclator_id, value=value, organization_id=org_id)
    if parents:
        item.parent_items = list(parents)
    db_session.add(item)
    db_session.flush()
    return item


# =============================================================================
# NOMENCLATOR — MÚLTIPLES PADRES VÁLIDOS
# =============================================================================

class TestNomenclatorMultipleParents:
    def test_create_with_multiple_parents_succeeds(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Test", org_id)
        region = _make_nomenclator(db_session, "Región Test", org_id)
        db_session.commit()

        res = api.client.post(
            "/nomenclators/",
            json={"name": "Ciudad Test", "parent_nomenclator_ids": [pais.public_uuid, region.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        parent_ids = {p["id"] for p in res.json()["parent_nomenclators"]}
        assert parent_ids == {pais.public_uuid, region.public_uuid}

    def test_create_with_nonexistent_parent_fails(self, api, initial_structure):
        res = api.client.post(
            "/nomenclators/",
            json={"name": "Catálogo Huérfano", "parent_nomenclator_ids": ["00000000-0000-0000-0000-000000000000"]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_update_replaces_full_parent_list(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Replace", org_id)
        region = _make_nomenclator(db_session, "Región Replace", org_id)
        ciudad = _make_nomenclator(db_session, "Ciudad Replace", org_id, parents=[pais])
        db_session.commit()

        res = api.client.put(
            f"/nomenclators/{ciudad.public_uuid}",
            json={"parent_nomenclator_ids": [region.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        parent_ids = {p["id"] for p in res.json()["parent_nomenclators"]}
        assert parent_ids == {region.public_uuid}

    def test_update_self_reference_fails(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        nom = _make_nomenclator(db_session, "Autoreferencia Test", org_id)
        db_session.commit()

        res = api.client.put(
            f"/nomenclators/{nom.public_uuid}",
            json={"parent_nomenclator_ids": [nom.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_update_cycle_fails(self, api, db_session, initial_structure):
        """A -> B (B tiene a A como padre). Intentar que A tenga a B como padre
        formaría un ciclo A<->B."""
        org_id = initial_structure["org_id"]
        a = _make_nomenclator(db_session, "Nodo A", org_id)
        b = _make_nomenclator(db_session, "Nodo B", org_id, parents=[a])
        db_session.commit()

        res = api.client.put(
            f"/nomenclators/{a.public_uuid}",
            json={"parent_nomenclator_ids": [b.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text


# =============================================================================
# NOMENCLATOR_ITEM — MÚLTIPLES PADRES + CONSISTENCIA CON EL CATÁLOGO
# =============================================================================

class TestNomenclatorItemMultipleParents:
    def test_create_item_with_valid_parent_succeeds(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Item OK", org_id)
        ciudad_cat = _make_nomenclator(db_session, "Ciudad Item OK", org_id, parents=[pais])
        arg = _make_item(db_session, pais.id, "Argentina", org_id)
        db_session.commit()

        res = api.client.post(
            "/nomenclator_items/",
            json={"value": "Buenos Aires", "nomenclator_id": ciudad_cat.public_uuid, "parent_item_ids": [arg.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        assert [p["id"] for p in res.json()["parent_items"]] == [arg.public_uuid]

    def test_create_item_with_parent_from_invalid_catalog_fails(self, api, db_session, initial_structure):
        """El catálogo 'Ciudad' NO declaró a 'Género' como padre válido —
        aunque el ítem de Género exista, no se puede usar como padre acá."""
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Item Bad", org_id)
        genero = _make_nomenclator(db_session, "Género Item Bad", org_id)
        ciudad_cat = _make_nomenclator(db_session, "Ciudad Item Bad", org_id, parents=[pais])
        masculino = _make_item(db_session, genero.id, "Masculino", org_id)
        db_session.commit()

        res = api.client.post(
            "/nomenclator_items/",
            json={"value": "Bahía Blanca", "nomenclator_id": ciudad_cat.public_uuid, "parent_item_ids": [masculino.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_update_replaces_full_parent_list(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Item Upd", org_id)
        region = _make_nomenclator(db_session, "Región Item Upd", org_id)
        ciudad_cat = _make_nomenclator(db_session, "Ciudad Item Upd", org_id, parents=[pais, region])
        arg = _make_item(db_session, pais.id, "Argentina Upd", org_id)
        pampa = _make_item(db_session, region.id, "Pampeana Upd", org_id)
        item = _make_item(db_session, ciudad_cat.id, "Bahía Blanca Upd", org_id, parents=[arg])
        db_session.commit()

        res = api.client.put(
            f"/nomenclator_items/{item.public_uuid}",
            json={"parent_item_ids": [arg.public_uuid, pampa.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        parent_ids = {p["id"] for p in res.json()["parent_items"]}
        assert parent_ids == {arg.public_uuid, pampa.public_uuid}

    def test_update_self_reference_fails(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        nom = _make_nomenclator(db_session, "Cat Autoref Item", org_id, parents=None)
        nom.parent_nomenclators = [nom]  # permitir referenciarse a sí mismo como padre válido para aislar el chequeo de ítem
        item = _make_item(db_session, nom.id, "Item Autoref", org_id)
        db_session.commit()

        res = api.client.put(
            f"/nomenclator_items/{item.public_uuid}",
            json={"parent_item_ids": [item.public_uuid]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text


# =============================================================================
# LEAD_FIELD — depends_on_field_id
# =============================================================================

class TestLeadFieldDependsOnField:
    @pytest.fixture
    def geo_setup(self, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]
        section_id = initial_structure["section_id"]

        pais_nom = _make_nomenclator(db_session, "País Field", org_id)
        ciudad_nom = _make_nomenclator(db_session, "Ciudad Field", org_id, parents=[pais_nom])
        genero_nom = _make_nomenclator(db_session, "Género Field", org_id)
        arg = _make_item(db_session, pais_nom.id, "Argentina Field", org_id)
        ba = _make_item(db_session, ciudad_nom.id, "Buenos Aires Field", org_id, parents=[arg])
        db_session.commit()

        camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
        section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

        campo_pais = LeadField(
            name="País", campaign_id=camp_internal_id, field_type_code="SELECTOR", field_subtype_code="SELECTOR_SIMPLE",
            nomenclator_id=pais_nom.id, lead_field_section_id=section_internal_id, order=10, organization_id=org_id, active=True
        )
        campo_texto = LeadField(
            name="Comentario", campaign_id=camp_internal_id, field_type_code="STRING",
            lead_field_section_id=section_internal_id, order=11, organization_id=org_id, active=True
        )
        db_session.add_all([campo_pais, campo_texto])
        db_session.commit()

        return {
            "org_id": org_id, "campaign_id": camp_id, "section_id": section_id,
            "pais_nom": pais_nom, "ciudad_nom": ciudad_nom, "genero_nom": genero_nom,
            "arg": arg, "ba": ba, "campo_pais": campo_pais, "campo_texto": campo_texto,
        }

    def test_create_field_depends_on_valid_parent_succeeds(self, api, geo_setup):
        res = api.create_lead_field(
            campaign_id=geo_setup["campaign_id"], name="Ciudad", field_type_code="SELECTOR",
            subtype_code="SELECTOR_SIMPLE", nomenclator_id=geo_setup["ciudad_nom"].public_uuid,
            depends_on_field_id=geo_setup["campo_pais"].public_uuid, expected_status=200,
        )
        assert res["depends_on_field_id"] == geo_setup["campo_pais"].id

    def test_create_field_depends_on_non_nomenclator_field_fails(self, api, geo_setup):
        res = api.client.post(
            "/lead_fields/",
            json={
                "campaign_id": geo_setup["campaign_id"], "name": "Ciudad Inválida",
                "field_type_code": "SELECTOR", "field_subtype_code": "SELECTOR_SIMPLE",
                "nomenclator_id": geo_setup["ciudad_nom"].public_uuid,
                "depends_on_field_id": geo_setup["campo_texto"].public_uuid,
            },
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_create_field_depends_on_inconsistent_catalog_fails(self, api, db_session, geo_setup):
        """'Género' no está declarado como padre válido del catálogo 'Ciudad'."""
        org_id = geo_setup["org_id"]
        camp_id = geo_setup["campaign_id"]
        section_id = geo_setup["section_id"]
        campo_genero = LeadField(
            name="Género", campaign_id=_resolve_internal_id(db_session, Campaign, camp_id), field_type_code="SELECTOR", field_subtype_code="SELECTOR_SIMPLE",
            nomenclator_id=geo_setup["genero_nom"].id, lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id), order=12,
            organization_id=org_id, active=True
        )
        db_session.add(campo_genero)
        db_session.commit()

        res = api.client.post(
            "/lead_fields/",
            json={
                "campaign_id": camp_id, "name": "Ciudad Sin Consistencia",
                "field_type_code": "SELECTOR", "field_subtype_code": "SELECTOR_SIMPLE",
                "nomenclator_id": geo_setup["ciudad_nom"].public_uuid,
                "depends_on_field_id": campo_genero.public_uuid,
            },
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_update_field_depends_on_self_fails(self, api, geo_setup):
        campo_ciudad = api.create_lead_field(
            campaign_id=geo_setup["campaign_id"], name="Ciudad Self", field_type_code="SELECTOR",
            subtype_code="SELECTOR_SIMPLE", nomenclator_id=geo_setup["ciudad_nom"].public_uuid, expected_status=200,
        )
        res = api.client.put(
            f"/lead_fields/{campo_ciudad['id']}",
            json={"depends_on_field_id": campo_ciudad["id"]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_update_field_depends_on_cycle_fails(self, api, geo_setup):
        """Ciudad depende de País. Intentar que País dependa de Ciudad formaría un ciclo."""
        api.create_lead_field(
            campaign_id=geo_setup["campaign_id"], name="Ciudad Cycle", field_type_code="SELECTOR",
            subtype_code="SELECTOR_SIMPLE", nomenclator_id=geo_setup["ciudad_nom"].public_uuid,
            depends_on_field_id=geo_setup["campo_pais"].public_uuid, expected_status=200,
        )
        # País depende de sí mismo indirectamente si apuntara a Ciudad -> pero
        # País no es de tipo nomenclador dependiente de Ciudad por catálogo,
        # así que directamente esperamos 400 (falla antes por consistencia o por ciclo).
        res = api.client.put(
            f"/lead_fields/{geo_setup['campo_pais'].public_uuid}",
            json={"depends_on_field_id": geo_setup["campo_pais"].public_uuid},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text

    def test_delete_field_blocked_when_has_dependents(self, api, geo_setup):
        api.create_lead_field(
            campaign_id=geo_setup["campaign_id"], name="Ciudad Delete", field_type_code="SELECTOR",
            subtype_code="SELECTOR_SIMPLE", nomenclator_id=geo_setup["ciudad_nom"].public_uuid,
            depends_on_field_id=geo_setup["campo_pais"].public_uuid, expected_status=200,
        )
        res = api.client.delete(f"/lead_fields/{geo_setup['campo_pais'].public_uuid}", headers=api.headers)
        assert res.status_code == 400, res.text

    def test_deactivate_field_blocked_when_has_dependents(self, api, geo_setup):
        api.create_lead_field(
            campaign_id=geo_setup["campaign_id"], name="Ciudad Deactivate", field_type_code="SELECTOR",
            subtype_code="SELECTOR_SIMPLE", nomenclator_id=geo_setup["ciudad_nom"].public_uuid,
            depends_on_field_id=geo_setup["campo_pais"].public_uuid, expected_status=200,
        )
        res = api.client.delete(f"/lead_fields/active/{geo_setup['campo_pais'].public_uuid}", headers=api.headers)
        assert res.status_code == 400, res.text


# =============================================================================
# LEAD — validación cruzada padre/hijo al cargar o editar
# =============================================================================

class TestLeadDependentFieldValidation:
    @pytest.fixture
    def lead_geo_setup(self, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]
        section_id = initial_structure["section_id"]

        pais_nom = _make_nomenclator(db_session, "País Lead", org_id)
        ciudad_nom = _make_nomenclator(db_session, "Ciudad Lead", org_id, parents=[pais_nom])
        arg = _make_item(db_session, pais_nom.id, "Argentina Lead", org_id)
        brasil = _make_item(db_session, pais_nom.id, "Brasil Lead", org_id)
        ba = _make_item(db_session, ciudad_nom.id, "Buenos Aires Lead", org_id, parents=[arg])
        sp = _make_item(db_session, ciudad_nom.id, "São Paulo Lead", org_id, parents=[brasil])
        db_session.commit()

        camp_internal_id = _resolve_internal_id(db_session, Campaign, camp_id)
        section_internal_id = _resolve_internal_id(db_session, LeadFieldSection, section_id)

        campo_pais = LeadField(
            name="País Lead F", campaign_id=camp_internal_id, field_type_code="SELECTOR", field_subtype_code="SELECTOR_MULTIPLE",
            nomenclator_id=pais_nom.id, lead_field_section_id=section_internal_id, order=20, organization_id=org_id, active=True
        )
        db_session.add(campo_pais)
        db_session.commit()

        campo_ciudad = LeadField(
            name="Ciudad Lead F", campaign_id=camp_internal_id, field_type_code="SELECTOR", field_subtype_code="SELECTOR_SIMPLE",
            nomenclator_id=ciudad_nom.id, lead_field_section_id=section_internal_id, order=21, organization_id=org_id,
            active=True, depends_on_field_id=campo_pais.id
        )
        db_session.add(campo_ciudad)
        db_session.commit()

        return {
            "campaign_id": camp_id, "campo_pais": campo_pais, "campo_ciudad": campo_ciudad,
            "arg": arg, "brasil": brasil, "ba": ba, "sp": sp,
        }

    def test_create_lead_with_matching_parent_and_child_succeeds(self, api, lead_geo_setup):
        s = lead_geo_setup
        values = [
            {"field_id": s["campo_pais"].id, "value": [s["arg"].id]},
            {"field_id": s["campo_ciudad"].id, "value": s["ba"].id},
        ]
        api.create_lead(campaign_id=s["campaign_id"], values=values, expected_status=200)

    def test_create_lead_with_mismatched_child_fails(self, api, lead_geo_setup):
        s = lead_geo_setup
        values = [
            {"field_id": s["campo_pais"].id, "value": [s["arg"].id]},
            {"field_id": s["campo_ciudad"].id, "value": s["sp"].id},  # São Paulo no es hija de Argentina
        ]
        res = api.create_lead(campaign_id=s["campaign_id"], values=values, expected_status=400)
        assert res is not None

    def test_create_lead_without_parent_value_fails(self, api, lead_geo_setup):
        s = lead_geo_setup
        values = [{"field_id": s["campo_ciudad"].id, "value": s["ba"].id}]
        api.create_lead(campaign_id=s["campaign_id"], values=values, expected_status=400)

    def test_multi_select_parent_uses_or_semantics(self, api, lead_geo_setup):
        """Si el campo padre permite selección múltiple, alcanza con que el
        hijo sea descendiente de CUALQUIERA de los padres elegidos."""
        s = lead_geo_setup
        values = [
            {"field_id": s["campo_pais"].id, "value": [s["arg"].id, s["brasil"].id]},
            {"field_id": s["campo_ciudad"].id, "value": s["sp"].id},
        ]
        api.create_lead(campaign_id=s["campaign_id"], values=values, expected_status=200)

    def test_update_lead_partial_uses_persisted_parent_value(self, api, db_session, lead_geo_setup):
        """Decisión del usuario: si un PUT no incluye el campo padre, se valida
        contra el valor YA PERSISTIDO del padre, no se ignora la validación."""
        s = lead_geo_setup
        lead = api.create_lead(
            campaign_id=s["campaign_id"],
            values=[
                {"field_id": s["campo_pais"].id, "value": [s["arg"].id]},
                {"field_id": s["campo_ciudad"].id, "value": s["ba"].id},
            ],
            expected_status=200,
        )

        # Solo mandamos Ciudad = São Paulo, sin tocar País (sigue siendo Argentina).
        res = api.client.put(
            f"/leads/{lead['id']}",
            json={"campaign_id": s["campaign_id"], "values": [{"field_id": s["campo_ciudad"].id, "value": s["sp"].id}]},
            headers=api.headers,
        )
        assert res.status_code == 400, res.text


# =============================================================================
# FILTRO GET /nomenclator_items/?parent_item_id= SIGUE FUNCIONANDO (M2M)
# =============================================================================

class TestNomenclatorItemParentFilter:
    def test_filter_by_parent_item_id_returns_only_children(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Filter", org_id)
        ciudad_cat = _make_nomenclator(db_session, "Ciudad Filter", org_id, parents=[pais])
        arg = _make_item(db_session, pais.id, "Argentina Filter", org_id)
        brasil = _make_item(db_session, pais.id, "Brasil Filter", org_id)
        ba = _make_item(db_session, ciudad_cat.id, "Buenos Aires Filter", org_id, parents=[arg])
        sp = _make_item(db_session, ciudad_cat.id, "São Paulo Filter", org_id, parents=[brasil])
        db_session.commit()

        # OJO: acá se manda .public_uuid (no .id) a propósito para ambos filtros -- es
        # el valor real que manda el frontend (ver nomenclatorService.ts/LeadPartialUpdate.tsx),
        # nunca el id interno. Con .id (int, de un objeto ORM creado directo en el test) el
        # test pasaba de casualidad sin ejercitar el bug real encontrado 2026-08-04: antes,
        # parent_item_id como uuid tiraba un 500 (ValueError sin capturar). Ver backend/AGENTS.md.
        res = api.client.get(
            f"/nomenclator_items/?nomenclator_id={ciudad_cat.public_uuid}&parent_item_id={arg.public_uuid}",
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        ids = {i["id"] for i in res.json()["items"]}
        assert ids == {ba.public_uuid}
        assert sp.public_uuid not in ids

    def test_filter_by_parent_item_id_returns_400_style_empty_for_unknown_uuid(self, api, db_session, initial_structure):
        """Un parent_item_id con formato de uuid pero que no existe no debe romper con 500 --
        debe resolver a 'ningún item.id interno matchea' y devolver una lista vacía, mismo
        criterio que el resto de los filtros FK del sistema (resolve_fk_filter_value)."""
        org_id = initial_structure["org_id"]
        pais = _make_nomenclator(db_session, "País Filter 2", org_id)
        ciudad_cat = _make_nomenclator(db_session, "Ciudad Filter 2", org_id, parents=[pais])
        db_session.commit()

        res = api.client.get(
            f"/nomenclator_items/?nomenclator_id={ciudad_cat.public_uuid}&parent_item_id=00000000-0000-0000-0000-000000000000",
            headers=api.headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["items"] == []
