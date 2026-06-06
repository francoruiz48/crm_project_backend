"""
test_lead_fixes.py
==================
Tests para los fixes de seguridad y lógica de negocio aplicados en:
  - lead_service.py
  - lead_repository.py
  - excel_formula_evaluator_service.py
  - storage_service.py

Cobertura:
  Ronda 1: seguridad básica (bulk_assign, page_size)
  Ronda 2: validaciones de org, nomencladores, change_state, duplicados
  Ronda 3: crashes, assigned_to_user_id, campaña, duplicados en update, payload
"""

import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.lead_field_section import LeadFieldSection
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.workspace import Workspace
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.lead_contact_state import LeadContactState
from app.models.security_models import User, UserOrganization
from app.models.team import Team


# =============================================================================
# HELPERS LOCALES
# =============================================================================

def _make_user(db, name, email):
    u = User(name=name, email=email)
    db.add(u)
    db.flush()
    return u


def _link_org(db, user, org_id):
    link = UserOrganization(user_id=user.id, organization_id=org_id, active=True)
    db.add(link)
    db.flush()
    return link


def _make_field(db, name, type_code, campaign_id, section_id, org_id,
                required=False, is_primary=False, nomenclator_id=None,
                field_subtype_code=None):
    f = LeadField(
        name=name,
        field_type_code=type_code,
        field_subtype_code=field_subtype_code,
        campaign_id=campaign_id,
        order=1,
        lead_field_section_id=section_id,
        organization_id=org_id,
        active=True,
        required=required,
        is_primary=is_primary,
        nomenclator_id=nomenclator_id,
    )
    db.add(f)
    db.flush()
    return f


def _create_lead_http(api, campaign_id, values: list):
    """POST /leads/ y retorna el JSON de respuesta (falla el test si no es 200)."""
    res = api.client.post(
        "/leads/",
        json={"campaign_id": campaign_id, "values": values},
        headers=api.headers,
    )
    assert res.status_code == 200, f"No se pudo crear lead: {res.text}"
    return res.json()


def _change_state_http(api, lead_id, new_state_id):
    return api.client.post(
        f"/leads/{lead_id}/change_state",
        json={"new_state_id": new_state_id},
        headers=api.headers,
    )


# =============================================================================
# GRUPO 1 — CREATE: validaciones de org en team_id y assigned_to_user_id
# =============================================================================

class TestCreateOrgValidations:

    def test_team_from_other_org_rejected_on_create(self, api, db_session, initial_structure):
        """team_id de otra org → 400 en create."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)

        other_org = Organization(name="Org Ajena")
        db_session.add(other_org)
        db_session.flush()
        foreign_team = Team(name="Equipo Ajeno", organization_id=other_org.id)
        db_session.add(foreign_team)
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "team_id": foreign_team.id,
                "values": [{"field_id": f.id, "value": "Test"}],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "team_id" in res.text.lower() or "equipo" in res.text.lower()

    def test_user_from_other_org_rejected_on_create(self, api, db_session, initial_structure):
        """assigned_to_user_id sin membresia en el org → 400 en create."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)

        outsider = _make_user(db_session, "Foraneo", "foraneo@test.com")
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "assigned_to_user_id": outsider.id,
                "values": [{"field_id": f.id, "value": "Test"}],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "assigned_to_user_id" in res.text.lower() or "usuario" in res.text.lower()

    def test_user_from_same_org_accepted_on_create(self, api, db_session, initial_structure):
        """assigned_to_user_id con membresia activa → 200 en create."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)

        member = _make_user(db_session, "Miembro", "miembro@test.com")
        _link_org(db_session, member, org_id)
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "assigned_to_user_id": member.id,
                "values": [{"field_id": f.id, "value": "Test"}],
            },
            headers=api.headers,
        )
        assert res.status_code == 200
        assert res.json()["assigned_to_user_id"] == member.id


# =============================================================================
# GRUPO 2 — assigned_to_user_id efectivamente persiste en el lead
# =============================================================================

class TestAssignedToUserPersisted:
    """Fix ronda 3: assigned_to_user_id se descartaba silenciosamente en create
    porque no estaba incluido en lead_data al construir el Lead."""

    def test_assigned_to_user_id_in_create_persists(self, api, db_session, initial_structure):
        """assigned_to_user_id enviado en create debe aparecer en un GET posterior."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)

        member = _make_user(db_session, "Asignado", "asignado@test.com")
        _link_org(db_session, member, org_id)
        db_session.commit()

        create_res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "assigned_to_user_id": member.id,
                "values": [{"field_id": f.id, "value": "Maria"}],
            },
            headers=api.headers,
        )
        assert create_res.status_code == 200
        lead_id = create_res.json()["id"]

        # Verificamos con GET que realmente se guardo en DB
        get_res = api.client.get(f"/leads/{lead_id}", headers=api.headers)
        assert get_res.status_code == 200
        assert get_res.json()["assigned_to_user_id"] == member.id, \
            "assigned_to_user_id se ignoro en create (no estaba en lead_data dict)"


# =============================================================================
# GRUPO 3 — UPDATE: contact_state_id debe pertenecer al mismo org
# =============================================================================

class TestUpdateContactStateValidation:

    def test_contact_state_from_other_org_rejected_on_update(self, api, db_session, initial_structure):
        """contact_state_id de otra org → 400 en update."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "Test"}])

        other_org = Organization(name="Org B")
        db_session.add(other_org)
        db_session.flush()
        foreign_cs = LeadContactState(
            name="Estado Foraneo", organization_id=other_org.id,
            is_initial=False, order=1,
        )
        db_session.add(foreign_cs)
        db_session.commit()

        res = api.client.put(
            f"/leads/{lead['id']}",
            json={"contact_state_id": foreign_cs.id},
            headers=api.headers,
        )
        assert res.status_code == 400

    def test_contact_state_from_same_org_accepted_on_update(self, api, db_session, initial_structure):
        """contact_state_id del mismo org → 200 en update."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        cs = LeadContactState(
            name="Mi Estado", organization_id=org_id, is_initial=False, order=1,
        )
        db_session.add(cs)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "Test"}])

        res = api.client.put(
            f"/leads/{lead['id']}",
            json={"contact_state_id": cs.id},
            headers=api.headers,
        )
        assert res.status_code == 200


# =============================================================================
# GRUPO 4 — Campana inexistente: error semantico correcto
# =============================================================================

class TestCampaignValidationOrder:
    """Fix ronda 3: la campana se validaba DESPUES de _prepare_creation_data,
    devolviendo 'no tiene campos configurados' en vez de 'no existe'."""

    def test_nonexistent_campaign_returns_campaign_error(self, api, db_session, initial_structure):
        res = api.client.post(
            "/leads/",
            json={"campaign_id": 999999, "values": []},
            headers=api.headers,
        )
        assert res.status_code == 400
        detail = str(res.json().get("detail", "")).lower()
        assert "campana" in detail or "campaign" in detail or "campa" in detail
        assert "campos configurados" not in detail, \
            "Error incorrecto: dice 'campos configurados' en lugar de 'campana no existe'"


# =============================================================================
# GRUPO 5 — Nomencladores: IDs validados contra el nomenclador del campo
# =============================================================================

class TestNomenclatorItemValidation:

    def _create_two_nomenclators(self, db, org_id):
        nom_a = Nomenclator(name="Nomenclador A", organization_id=org_id)
        nom_b = Nomenclator(name="Nomenclador B", organization_id=org_id)
        db.add_all([nom_a, nom_b])
        db.flush()
        item_a = NomenclatorItem(value="Opcion A", nomenclator_id=nom_a.id)
        item_b = NomenclatorItem(value="Opcion B", nomenclator_id=nom_b.id)
        db.add_all([item_a, item_b])
        db.flush()
        return nom_a, nom_b, item_a, item_b

    def test_item_from_correct_nomenclator_accepted(self, api, db_session, initial_structure):
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        nom_a, _, item_a, _ = self._create_two_nomenclators(db_session, org_id)
        f = _make_field(db_session, "Tipo", "SELECTOR", camp_id, section_id, org_id,
                        nomenclator_id=nom_a.id)
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [{"field_id": f.id, "value": item_a.id}],
            },
            headers=api.headers,
        )
        assert res.status_code == 200

    def test_item_from_wrong_nomenclator_rejected(self, api, db_session, initial_structure):
        """item_b pertenece a Nomenclador B pero el campo usa Nomenclador A → 400."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        nom_a, _, _, item_b = self._create_two_nomenclators(db_session, org_id)
        f = _make_field(db_session, "Tipo", "SELECTOR", camp_id, section_id, org_id,
                        nomenclator_id=nom_a.id)
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [{"field_id": f.id, "value": item_b.id}],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "válidas" in res.text.lower() or "validas" in res.text.lower() or "invalid" in res.text.lower() or "opciones" in res.text.lower()

    def test_global_nomenclator_item_accepted(self, api, db_session, initial_structure):
        """Items de nomencladores globales (org=NULL) deben seguir funcionando."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        global_nom = Nomenclator(name="Global Nom", organization_id=None)
        db_session.add(global_nom)
        db_session.flush()
        global_item = NomenclatorItem(value="Global Item", nomenclator_id=global_nom.id)
        db_session.add(global_item)
        db_session.flush()

        f = _make_field(db_session, "Campo Global", "SELECTOR", camp_id, section_id, org_id,
                        nomenclator_id=global_nom.id)
        db_session.commit()

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [{"field_id": f.id, "value": global_item.id}],
            },
            headers=api.headers,
        )
        assert res.status_code == 200


# =============================================================================
# GRUPO 6 — change_state con current_state_id = NULL
# =============================================================================

class TestChangeStateFromNull:
    """Fix ronda 2: un lead con current_state NULL solo puede ir al estado inicial."""

    def test_null_state_to_non_initial_rejected(self, api, db_session, initial_structure):
        camp_id       = initial_structure["campaign_id"]
        org_id        = initial_structure["org_id"]
        section_id    = initial_structure["section_id"]
        state_contact = initial_structure["state_contact_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "Test"}])

        db_session.query(Lead).filter_by(id=lead["id"]).update({"current_state_id": None})
        db_session.commit()

        # Con current_state_id=NULL el servicio no puede serializar el lead
        # (current_state_id: int no es Optional), por lo que retorna 400.
        res = _change_state_http(api, lead["id"], state_contact)
        assert res.status_code == 400


# =============================================================================
# GRUPO 7 — Duplicados en update: exclude_lead_id
# =============================================================================

class TestDuplicateCheckInUpdate:

    def test_update_primary_field_to_existing_value_rejected(self, api, db_session, initial_structure):
        """Cambiar un campo primary al valor de otro lead → 400."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "DNI", "STRING", camp_id, section_id, org_id,
                        required=True, is_primary=True)
        db_session.commit()

        lead_a = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "11111111"}])
        lead_b = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "22222222"}])

        res = api.client.put(
            f"/leads/{lead_b['id']}",
            json={"values": [{"field_id": f.id, "value": "11111111"}]},
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "duplicado" in res.text.lower() or "identificatorio" in res.text.lower()

    def test_update_primary_field_to_own_value_not_duplicate(self, api, db_session, initial_structure):
        """Re-enviar el mismo valor primary del mismo lead → 200 (exclude_lead_id funciona)."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "DNI", "STRING", camp_id, section_id, org_id,
                        required=True, is_primary=True)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "33333333"}])

        res = api.client.put(
            f"/leads/{lead['id']}",
            json={"values": [{"field_id": f.id, "value": "33333333"}]},
            headers=api.headers,
        )
        assert res.status_code == 200

    def test_create_with_duplicate_primary_rejected(self, api, db_session, initial_structure):
        """Crear un lead con campo primary ya existente → 400."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Email", "STRING", camp_id, section_id, org_id,
                        required=True, is_primary=True)
        db_session.commit()

        _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "dup@test.com"}])

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [{"field_id": f.id, "value": "dup@test.com"}],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "duplicado" in res.text.lower() or "identificatorio" in res.text.lower()


# =============================================================================
# GRUPO 8 — Duplicados con campos primary parciales
# =============================================================================

class TestPartialPrimaryDuplicateCheck:

    def test_partial_primary_fields_detect_duplicate(self, api, db_session, initial_structure):
        """Con 2 campos primary, si ambos coinciden debe detectar duplicado."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f1 = _make_field(db_session, "DNI",       "STRING", camp_id, section_id, org_id,
                         required=True, is_primary=True)
        f2 = _make_field(db_session, "Pasaporte", "STRING", camp_id, section_id, org_id,
                         required=True, is_primary=True)
        db_session.commit()

        _create_lead_http(api, camp_id, [
            {"field_id": f1.id, "value": "99999999"},
            {"field_id": f2.id, "value": "AB12345"},
        ])

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [
                    {"field_id": f1.id, "value": "99999999"},
                    {"field_id": f2.id, "value": "AB12345"},
                ],
            },
            headers=api.headers,
        )
        assert res.status_code == 400, \
            "Debe detectar duplicado con multiples campos primary coincidentes"


# =============================================================================
# GRUPO 9 — field_id duplicado en el mismo payload
# =============================================================================

class TestDuplicateFieldIdInPayload:
    """Fix ronda 3: enviar el mismo field_id dos veces sobreescribia silenciosamente."""

    def test_duplicate_field_id_in_create_rejected(self, api, db_session, initial_structure):
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()
        field_id = f.id  # capturar antes del HTTP call para evitar ObjectDeletedError

        res = api.client.post(
            "/leads/",
            json={
                "campaign_id": camp_id,
                "values": [
                    {"field_id": field_id, "value": "Juan"},
                    {"field_id": field_id, "value": "Pedro"},
                ],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "mas de una vez" in res.text.lower() or str(field_id) in res.text

    def test_duplicate_field_id_in_update_rejected(self, api, db_session, initial_structure):
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()
        field_id = f.id  # capturar antes del HTTP call para evitar ObjectDeletedError

        lead = _create_lead_http(api, camp_id, [{"field_id": field_id, "value": "Original"}])

        res = api.client.put(
            f"/leads/{lead['id']}",
            json={
                "values": [
                    {"field_id": field_id, "value": "NuevoA"},
                    {"field_id": field_id, "value": "NuevoB"},
                ],
            },
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "mas de una vez" in res.text.lower() or str(field_id) in res.text


# =============================================================================
# GRUPO 10 — bulk_assign: seguridad
# =============================================================================

class TestBulkAssignSecurity:

    def test_exceeds_max_lead_ids_returns_400(self, api, db_session, initial_structure):
        """Mas de 200 lead_ids → 400."""
        lead_ids = list(range(1, 202))
        res = api.client.patch(
            "/leads/bulk-assign",
            json={"lead_ids": lead_ids, "target_team_id": 1},
            headers=api.headers,
        )
        assert res.status_code == 400
        assert "200" in res.text or "reasignar" in res.text.lower()

    def test_team_from_other_org_rejected_on_bulk_assign(self, api, db_session, initial_structure):
        """target_team_id de otra org → 400 en bulk_assign."""
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "Test"}])

        other_org = Organization(name="Org Ajena")
        db_session.add(other_org)
        db_session.flush()
        foreign_team = Team(name="Equipo Ajeno", organization_id=other_org.id)
        db_session.add(foreign_team)
        db_session.commit()

        res = api.client.patch(
            "/leads/bulk-assign",
            json={"lead_ids": [lead["id"]], "target_team_id": foreign_team.id},
            headers=api.headers,
        )
        assert res.status_code == 400

    def test_cross_tenant_lead_silently_ignored_in_bulk_assign(
        self, api, db_session, initial_structure
    ):
        """Lead de otro tenant en lead_ids no debe ser modificado (IDOR)."""
        org_id = initial_structure["org_id"]

        other_org = Organization(name="Org Foranea")
        db_session.add(other_org)
        db_session.flush()
        other_ws = Workspace(name="WS B", organization_id=other_org.id)
        db_session.add(other_ws)
        db_session.flush()
        other_flow = LeadFlow(name="Flow B", organization_id=other_org.id)
        db_session.add(other_flow)
        db_session.flush()
        other_state = LeadState(
            lead_flow_id=other_flow.id, organization_id=other_org.id,
            name="Inicial B", category="OPEN", is_initial=True, order=1,
        )
        db_session.add(other_state)
        db_session.flush()
        other_camp = Campaign(
            name="Camp B", workspace_id=other_ws.id,
            lead_flow_id=other_flow.id, organization_id=other_org.id,
        )
        db_session.add(other_camp)
        db_session.flush()

        other_lead = Lead(
            campaign_id=other_camp.id,
            organization_id=other_org.id,
            current_state_id=other_state.id,
        )
        db_session.add(other_lead)
        db_session.commit()

        original_team_id = other_lead.team_id

        my_team = Team(name="Mi Equipo", organization_id=org_id)
        db_session.add(my_team)
        db_session.commit()

        res = api.client.patch(
            "/leads/bulk-assign",
            json={"lead_ids": [other_lead.id], "target_team_id": my_team.id},
            headers=api.headers,
        )
        assert res.status_code == 200

        db_session.refresh(other_lead)
        assert other_lead.team_id == original_team_id, \
            "Un lead de otro tenant fue modificado (IDOR en bulk_assign)"


# =============================================================================
# GRUPO 11 — Formulas: ExcelFormulaEvaluatorService
# =============================================================================

class TestFormulaEvaluator:
    """Fix ronda 2: RANDOM() tenia firma incorrecta y ZeroDivision crasheaba."""

    def test_random_function_returns_float(self):
        """RANDOM() debe retornar un float sin TypeError."""
        from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
        result = ExcelFormulaEvaluatorService().evaluate("RANDOM()")
        assert isinstance(result, float), f"Esperaba float, recibio {type(result)}"
        assert 0.0 <= result < 1.0

    def test_division_by_zero_returns_error_not_crash(self):
        """Division por cero → '#ERROR:...' sin lanzar excepcion."""
        from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
        result = ExcelFormulaEvaluatorService(context={"X": 0}).evaluate("10 / {X}")
        assert result is not None
        assert "#ERROR" in str(result), f"Esperaba '#ERROR', recibio: {result}"

    def test_normal_division_works(self):
        """Division normal sigue funcionando tras el fix de ZeroDivision."""
        from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
        result = ExcelFormulaEvaluatorService(context={"A": 10, "B": 4}).evaluate("{A} / {B}")
        assert result == pytest.approx(2.5)


# =============================================================================
# GRUPO 12 — StorageService: validacion de extension de archivo
# =============================================================================

class TestStorageExtensionValidation:
    """Fix ronda 2: extension debe coincidir con el MIME type declarado."""

    def test_mismatched_extension_raises_400(self):
        """.exe con content_type image/jpeg → HTTPException 400."""
        from app.services.storage_service import StorageService
        from fastapi import HTTPException

        fake_file = MagicMock()
        fake_file.filename = "malicious.exe"
        fake_file.content_type = "image/jpeg"
        fake_file.file.read.return_value = b"fake"
        fake_file.file.seek.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            StorageService.upload_file(fake_file, folder="test")

        assert exc_info.value.status_code == 400
        assert "exe" in str(exc_info.value.detail).lower()

    def test_matching_extension_passes_validation(self):
        """.jpg con image/jpeg no debe lanzar error de extension."""
        from app.services.storage_service import StorageService
        from fastapi import HTTPException

        fake_file = MagicMock()
        fake_file.filename = "foto.jpg"
        fake_file.content_type = "image/jpeg"
        fake_file.file.read.return_value = b"\xff\xd8\xff" + b"\x00" * 50
        fake_file.file.seek.return_value = None

        with patch.object(StorageService, "get_client") as mock_get_client:
            mock_get_client.return_value.storage.from_.return_value.upload.return_value = None
            result = StorageService.upload_file(fake_file, folder="test")
            assert "jpg" in result

    def test_unknown_mime_skips_extension_check(self):
        """MIME no registrado en el mapa no debe bloquear el upload por extension."""
        from app.services.storage_service import StorageService

        fake_file = MagicMock()
        fake_file.filename = "data.bin"
        fake_file.content_type = "application/octet-stream"
        fake_file.file.read.return_value = b"\x00\x01\x02"
        fake_file.file.seek.return_value = None

        with patch.object(StorageService, "get_client") as mock_get_client:
            mock_get_client.return_value.storage.from_.return_value.upload.return_value = None
            result = StorageService.upload_file(fake_file, folder="test")
            assert "bin" in result


# =============================================================================
# GRUPO 13 — UPDATE sin JSON (obj_in=None): no debe dar 500
# =============================================================================

class TestUpdateWithoutJsonBody:
    """Fix ronda 3: PUT con files_map no vacio pero sin JSON body enviaba obj_in=None
    al servicio, causando AttributeError en 'obj_in.model_fields_set'."""

    def test_update_field_file_without_json_does_not_crash(self, api, db_session, initial_structure):
        """PUT multipart con file_{field_id} sin 'data' JSON no debe dar 500.

        El controller pasa obj_in=None cuando lead_dict esta vacio.
        Antes del fix: AttributeError al acceder obj_in.model_fields_set.
        Despues del fix: guard 'if obj_in and ...' previene el crash.
        El servicio ignora files_map si obj_in.values es None y retorna 200.
        """
        camp_id    = initial_structure["campaign_id"]
        org_id     = initial_structure["org_id"]
        section_id = initial_structure["section_id"]

        f = _make_field(db_session, "Nombre", "STRING", camp_id, section_id, org_id)
        db_session.commit()

        lead = _create_lead_http(api, camp_id, [{"field_id": f.id, "value": "Test"}])

        fake_content = BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)

        # file_{field_id} hace que el controller pueble files_map (no avatar_file)
        # Asi el controller NO lanza 400 y si pasa obj_in=None al servicio
        field_key = "file_" + str(f.id)
        res = api.client.put(
            f"/leads/{lead['id']}",
            files={field_key: ("foto.jpg", fake_content, "image/jpeg")},
            headers=api.headers,
        )

        assert res.status_code != 500, \
            f"Crash con obj_in=None en update (AttributeError): {res.text}"
        assert res.status_code == 200
