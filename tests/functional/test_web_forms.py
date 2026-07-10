"""
test_web_forms.py
===================
Cobertura del hallazgo #4 de la auditoría (2026-07-10): `WebForm` era el único
de los 21 módulos documentados sin NINGÚN test, a pesar de ser el módulo con
mayor superficie de ataque del sistema (único endpoint de escritura público,
sin autenticación). Ver docs/formularios_web.md.

No es un bug puntual como los hallazgos #1-#3: es un hueco de cobertura. Estos
tests ejercitan:
  - El CRUD privado (`/web_forms`) y sus validaciones anti-IDOR de campos.
  - Las 4 barreras de seguridad del submit público (honeypot, CAPTCHA,
    validación de origen, rate limit) descriptas en formularios_web.md §5.
  - La inyección forzada de `hidden_value` (formularios_web.md §6).

Notas sobre decisiones de testing:
  - El CAPTCHA se mockea (`httpx.AsyncClient.post`) para no depender de un
    servicio externo real ni de las env vars CAPTCHA_SECRET_KEY/CAPTCHA_VERIFY_URL.
  - El rate limit usa una instancia de `Limiter` propia del router
    (`web_form_public_controller.limiter`), separada de la de `app.main`. No
    se pudo confirmar en este entorno (sin poder correr pytest) que el
    comportamiento sea idéntico al de producción; si el test de rate limit
    falla, es el primer lugar a revisar. Se llama a `limiter.reset()` antes
    del test para no depender del orden de ejecución de la suite (la
    instancia vive a nivel de módulo y persiste contadores entre tests).
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.web_form import WebForm
from app.models.web_form_field import WebFormField
from app.controllers.web_form_public_controller import limiter as public_forms_limiter


# =============================================================================
# HELPERS
# =============================================================================

def _create_web_form_db(db_session, org_id, campaign_id, **overrides):
    """Crea un WebForm directo en la DB (sin pasar por el endpoint privado),
    para no acoplar los tests del área pública al área privada."""
    defaults = dict(
        organization_id=org_id,
        campaign_id=campaign_id,
        name="Formulario de Test",
        title="Dejanos tus datos",
        require_captcha=False,
        allowed_domains=[],
        active=True,
    )
    defaults.update(overrides)
    form = WebForm(**defaults)
    db_session.add(form)
    db_session.commit()
    return form


def _add_web_form_field(db_session, web_form_id, lead_field_id, **overrides):
    defaults = dict(web_form_id=web_form_id, lead_field_id=lead_field_id, order=1)
    defaults.update(overrides)
    field = WebFormField(**defaults)
    db_session.add(field)
    db_session.commit()
    return field


# =============================================================================
# CRUD PRIVADO (/web_forms) — anti-IDOR y reglas de negocio
# =============================================================================

class TestWebFormPrivateCRUD:
    def test_create_web_form_success(self, api, initial_structure, initial_fields):
        campaign_id = initial_structure["campaign_id"]
        nombre_id = initial_fields["nombre_id"]

        resp = api.client.post(
            "/web_forms/",
            json={
                "name": "Landing Ventas",
                "campaign_id": campaign_id,
                "fields": [{"lead_field_id": nombre_id, "order": 1}],
            },
            headers=api.headers,
        )
        assert resp.status_code in (200, 201), resp.text
        body = resp.json()
        assert body["public_uuid"]
        assert body["campaign_id"] == campaign_id

    def test_create_web_form_rejects_duplicate_field_ids(self, api, initial_structure, initial_fields):
        """Regla 1 de _validate_form_fields: no se puede repetir el mismo lead_field_id."""
        campaign_id = initial_structure["campaign_id"]
        nombre_id = initial_fields["nombre_id"]

        resp = api.client.post(
            "/web_forms/",
            json={
                "name": "Form Duplicado",
                "campaign_id": campaign_id,
                "fields": [
                    {"lead_field_id": nombre_id, "order": 1},
                    {"lead_field_id": nombre_id, "order": 2},
                ],
            },
            headers=api.headers,
        )
        assert resp.status_code == 400
        assert "más de una vez" in resp.text

    def test_create_web_form_rejects_field_from_other_campaign(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Anti-IDOR: un lead_field_id que pertenece a OTRA campaña debe ser rechazado,
        aunque el campo exista y esté activo."""
        campaign_id = initial_structure["campaign_id"]
        org_id = initial_structure["org_id"]

        other_campaign = api.create_campaign(
            workspace_id=initial_structure["workspace_id"],
            name="Otra Campaña",
            lead_flow_id=initial_structure["lead_flow_id"],
        )
        other_field = LeadField(
            name="Campo Ajeno",
            field_type_code="STRING",
            campaign_id=other_campaign["id"],
            organization_id=org_id,
            lead_field_section_id=initial_structure["section_id"],
            order=1,
            active=True,
        )
        db_session.add(other_field)
        db_session.commit()

        resp = api.client.post(
            "/web_forms/",
            json={
                "name": "Form IDOR",
                "campaign_id": campaign_id,
                "fields": [{"lead_field_id": other_field.id, "order": 1}],
            },
            headers=api.headers,
        )
        assert resp.status_code == 400
        assert "otra campaña" in resp.text

    def test_create_web_form_rejects_inactive_field(self, api, db_session, initial_structure):
        campaign_id = initial_structure["campaign_id"]
        org_id = initial_structure["org_id"]

        inactive_field = LeadField(
            name="Campo Inactivo",
            field_type_code="STRING",
            campaign_id=campaign_id,
            organization_id=org_id,
            lead_field_section_id=initial_structure["section_id"],
            order=1,
            active=False,
        )
        db_session.add(inactive_field)
        db_session.commit()

        resp = api.client.post(
            "/web_forms/",
            json={
                "name": "Form Campo Inactivo",
                "campaign_id": campaign_id,
                "fields": [{"lead_field_id": inactive_field.id, "order": 1}],
            },
            headers=api.headers,
        )
        assert resp.status_code == 400
        assert "inactivo" in resp.text

    def test_update_web_form_replaces_fields_totally(self, api, db_session, initial_structure, initial_fields):
        """Al actualizar con `fields`, es reemplazo total (no merge parcial)."""
        campaign_id = initial_structure["campaign_id"]
        nombre_id = initial_fields["nombre_id"]
        edad_id = initial_fields["edad_id"]

        created = api.client.post(
            "/web_forms/",
            json={
                "name": "Form a Editar",
                "campaign_id": campaign_id,
                "fields": [{"lead_field_id": nombre_id, "order": 1}],
            },
            headers=api.headers,
        ).json()

        resp = api.client.put(
            f"/web_forms/{created['id']}",
            json={"fields": [{"lead_field_id": edad_id, "order": 1}]},
            headers=api.headers,
        )
        assert resp.status_code == 200, resp.text
        remaining = db_session.query(WebFormField).filter_by(web_form_id=created["id"]).all()
        assert len(remaining) == 1
        assert remaining[0].lead_field_id == edad_id


# =============================================================================
# ENDPOINT PÚBLICO — GET /public/forms/{uuid}
# =============================================================================

class TestPublicFormGet:
    def test_get_public_form_returns_config_without_leaking_org_or_campaign(
        self, api, db_session, initial_structure, initial_fields
    ):
        form = _create_web_form_db(db_session, initial_structure["org_id"], initial_structure["campaign_id"])
        _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.get(f"/public/forms/{form.public_uuid}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["public_uuid"] == form.public_uuid
        assert "organization_id" not in body
        assert "campaign_id" not in body

    def test_get_public_form_unknown_uuid_returns_404(self, api):
        resp = api.client.get("/public/forms/uuid-que-no-existe")
        assert resp.status_code == 404

    def test_get_public_form_inactive_returns_404(self, api, db_session, initial_structure):
        form = _create_web_form_db(db_session, initial_structure["org_id"], initial_structure["campaign_id"], active=False)
        resp = api.client.get(f"/public/forms/{form.public_uuid}")
        assert resp.status_code == 404


# =============================================================================
# ENDPOINT PÚBLICO — POST /public/forms/{uuid}/submit — las 4 barreras
# =============================================================================

class TestPublicFormSubmit:
    @pytest.fixture(autouse=True)
    def _reset_rate_limiter(self):
        """El Limiter del router público vive a nivel de módulo y sus contadores
        persisten mientras dure el proceso de test. Sin este reset, los tests de
        esta clase se irían pisando la cuota de '5/minute' entre sí (todos pegan
        al mismo endpoint desde la misma IP simulada de TestClient)."""
        public_forms_limiter.reset()
        yield

    def test_submit_creates_lead_happy_path(self, api, db_session, initial_structure, initial_fields):
        form = _create_web_form_db(db_session, initial_structure["org_id"], initial_structure["campaign_id"])
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={str(wf_field.id): "Juan Pérez", "website_url_ext": ""},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

        leads = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).all()
        assert len(leads) == 1
        values = {fv.field_id: fv.value for fv in leads[0].field_values}
        assert values.get(initial_fields["nombre_id"]) == "Juan Pérez"
        # El lead público no tiene usuario logueado que lo haya creado.
        assert leads[0].created_by is None

    def test_submit_honeypot_filled_fakes_success_without_creating_lead(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Barrera 2: si el campo honeypot viene relleno, se responde 200 falso
        pero NO se crea ningún lead."""
        form = _create_web_form_db(db_session, initial_structure["org_id"], initial_structure["campaign_id"])
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={str(wf_field.id): "Bot", "website_url_ext": "http://bot-fill.example"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        leads = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).all()
        assert len(leads) == 0

    def test_submit_hidden_value_is_injected_and_cannot_be_overridden(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Barrera de formularios_web.md §6: un campo con hidden_value se fuerza
        server-side, aunque el visitante intente mandar otro valor para esa clave."""
        form = _create_web_form_db(db_session, initial_structure["org_id"], initial_structure["campaign_id"])
        hidden_field = _add_web_form_field(
            db_session, form.id, initial_fields["edad_id"], hidden_value="99", order=2
        )
        visible_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"], order=1)

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={
                str(visible_field.id): "Ana",
                str(hidden_field.id): "Valor Intentando Sobreescribir",
                "website_url_ext": "",
            },
        )
        assert resp.status_code == 200, resp.text

        lead = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).first()
        values = {fv.field_id: fv.value for fv in lead.field_values}
        assert values.get(initial_fields["edad_id"]) == "99"

    def test_submit_requires_captcha_token_when_form_demands_it(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Barrera 3, parte 1: sin captcha_token en el payload, 400 antes de llamar
        al servicio de verificación externo."""
        form = _create_web_form_db(
            db_session, initial_structure["org_id"], initial_structure["campaign_id"], require_captcha=True
        )
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={str(wf_field.id): "Juan", "website_url_ext": ""},
        )
        assert resp.status_code == 400
        assert "token de verificación" in resp.text

    def test_submit_captcha_verification_failure_is_rejected(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Barrera 3, parte 2: token presente pero el servicio externo dice que no es válido → 400."""
        form = _create_web_form_db(
            db_session, initial_structure["org_id"], initial_structure["campaign_id"], require_captcha=True
        )
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        fake_response = AsyncMock()
        fake_response.json = lambda: {"success": False}
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=fake_response)):
            resp = api.client.post(
                f"/public/forms/{form.public_uuid}/submit",
                json={str(wf_field.id): "Juan", "captcha_token": "token-invalido", "website_url_ext": ""},
            )
        assert resp.status_code == 400
        assert "verificar" in resp.text.lower()

        leads = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).all()
        assert len(leads) == 0

    def test_submit_captcha_verification_success_creates_lead(
        self, api, db_session, initial_structure, initial_fields
    ):
        form = _create_web_form_db(
            db_session, initial_structure["org_id"], initial_structure["campaign_id"], require_captcha=True
        )
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        fake_response = AsyncMock()
        fake_response.json = lambda: {"success": True}
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=fake_response)):
            resp = api.client.post(
                f"/public/forms/{form.public_uuid}/submit",
                json={str(wf_field.id): "Juan", "captcha_token": "token-valido", "website_url_ext": ""},
            )
        assert resp.status_code == 200, resp.text

        leads = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).all()
        assert len(leads) == 1

    def test_submit_blocks_disallowed_origin(self, api, db_session, initial_structure, initial_fields):
        """Barrera 4: si el formulario tiene allowed_domains configurado, un Origin
        que no matchea ninguno debe ser rechazado con 403."""
        form = _create_web_form_db(
            db_session,
            initial_structure["org_id"],
            initial_structure["campaign_id"],
            allowed_domains=["miweb.com"],
        )
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={str(wf_field.id): "Juan", "website_url_ext": ""},
            headers={"Origin": "https://sitio-no-autorizado.com"},
        )
        assert resp.status_code == 403

        leads = db_session.query(Lead).filter_by(campaign_id=initial_structure["campaign_id"]).all()
        assert len(leads) == 0

    def test_submit_allows_matching_origin(self, api, db_session, initial_structure, initial_fields):
        form = _create_web_form_db(
            db_session,
            initial_structure["org_id"],
            initial_structure["campaign_id"],
            allowed_domains=["miweb.com"],
        )
        wf_field = _add_web_form_field(db_session, form.id, initial_fields["nombre_id"])

        resp = api.client.post(
            f"/public/forms/{form.public_uuid}/submit",
            json={str(wf_field.id): "Juan", "website_url_ext": ""},
            headers={"Origin": "https://www.miweb.com"},
        )
        assert resp.status_code == 200, resp.text

    def test_submit_rate_limited_after_five_per_minute(self, api, db_session, initial_structure, initial_fields):
        """Barrera 1: máximo 5 envíos por minuto por IP. Usamos un UUID inexistente
        para no depender de la lógica de negocio (el rate limit corre ANTES, vía
        decorador, así que igual debería bloquear en el 6to intento con 429)."""

        statuses = []
        for _ in range(6):
            resp = api.client.post(
                "/public/forms/uuid-inexistente-rate-limit/submit",
                json={"website_url_ext": ""},
            )
            statuses.append(resp.status_code)

        assert 429 in statuses, f"Se esperaba al menos un 429 entre los 6 intentos, se obtuvo: {statuses}"
        # Los primeros (antes de agotar la cuota) deben fallar por 404 (form no existe),
        # no por otro motivo distinto al rate limit.
        assert all(s in (404, 429) for s in statuses)
