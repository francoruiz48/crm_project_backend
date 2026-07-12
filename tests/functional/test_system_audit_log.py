"""
test_system_audit_log.py
==========================
Cobertura del hallazgo #5 de la auditoría (2026-07-10): `_log_audit`
(`app/services/base_service.py`) seteaba `organization_id=getattr(obj,
"organization_id", None)` — si el modelo auditado no tiene esa columna (ej.
`LeadComment`, `FieldAutomation`, `TeamMember`, `TeamAccess`,
`LeadStateTransition`, `LeadFieldSubtype`, `LeadFieldType`), la fila de
`SystemAuditLog` quedaba con `organization_id=NULL`. El filtro de tenant de
lectura (`_apply_tenant_filter`) filtra por `organization_id == org_id OR
organization_id == ADMIN_ORG_ID` — una fila NULL no matchea ninguna de las
dos (semántica SQL de NULL), así que quedaba invisible por API para
cualquier organización, para siempre. Ver docs/auditoria.md §7.

`LeadComment` es el caso de prueba: su service no tiene ningún override
sobre el CRUD genérico, así que ejercita el flujo real de `_log_audit` sin
lógica adicional de por medio.

Fix aplicado: `_log_audit` ahora usa `TENANT_ORG_ID.get()` (la organización
activa del request) como fallback cuando el objeto auditado no tiene
`organization_id` propio.

**Regresión detectada tras el primer fix (2026-07-10, en producción):** la
primera versión del fallback usaba `TENANT_ORG_ID.get()` a ciegas, sin
validar que esa organización existiera. `system_audit_log.organization_id`
tiene un FK real contra `organization.id` (no es solo `nullable=True`), y
`OrganizationController` no exige que el header `X-Organization-Id` sea una
org real para `create`/`read` (`_get_deps` devuelve `[]` para esas acciones,
ver `usuarios_y_permisos.md`). Al crear una organización nueva con ese header
apuntando a un id inexistente, el `INSERT` en `system_audit_log` violaba la
FK y **abortaba la creación entera de la organización** con un 500 —
mucho peor que el bug original. Se corrigió con dos cambios en `_log_audit`:
(1) si el modelo auditado es la propia `Organization`, se usa `obj.id` (su
propio id, ya garantizado válido por el `flush()` previo) en vez del header;
(2) para cualquier otro modelo, se verifica con una query que la organización
del `TENANT_ORG_ID` realmente exista antes de usarla — si no existe, se cae
de nuevo a `NULL` (el comportamiento viejo, seguro) en vez de reventar.
"""
from app.core.constans import ADMIN_ORG_ID
from app.core.context import TENANT_ORG_ID
from app.models.audit.system_audit_log import SystemAuditLog
from app.models.lead_comment import LeadComment
from app.services.lead_comment_service import LeadCommentService


def _create_lead(api, campaign_id, nombre_field_id):
    return api.create_lead(
        campaign_id=campaign_id,
        values=[{"field_id": nombre_field_id, "value": "Lead de Test"}],
    )


class TestAuditLogOrganizationIdFallback:
    def test_lead_comment_audit_row_gets_organization_id_not_null(
        self, api, db_session, initial_structure, initial_fields
    ):
        """Regresión directa del bug: antes del fix, esta fila quedaba con
        organization_id=NULL."""
        org_id = initial_structure["org_id"]
        lead = _create_lead(api, initial_structure["campaign_id"], initial_fields["nombre_id"])

        resp = api.client.post(
            "/lead_comments/",
            json={"lead_id": lead["id"], "content": "Un comentario de prueba"},
            headers=api.headers,
        )
        assert resp.status_code in (200, 201), resp.text
        comment_id = resp.json()["id"]

        audit_row = (
            db_session.query(SystemAuditLog)
            .filter_by(entity_type="LeadComment", entity_id=comment_id)
            .first()
        )
        assert audit_row is not None, "No se encontró la fila de auditoría del comentario."
        assert audit_row.organization_id == org_id
        assert audit_row.organization_id is not None

    def test_lead_comment_audit_row_visible_via_audit_logs_endpoint(
        self, api, initial_structure, initial_fields
    ):
        """Confirma el efecto visible del fix: la fila ya no queda huérfana,
        aparece en GET /audit-logs/ para la organización que hizo la acción."""
        lead = _create_lead(api, initial_structure["campaign_id"], initial_fields["nombre_id"])

        resp = api.client.post(
            "/lead_comments/",
            json={"lead_id": lead["id"], "content": "Otro comentario"},
            headers=api.headers,
        )
        assert resp.status_code in (200, 201), resp.text
        comment_id = resp.json()["id"]

        resp_audit = api.client.get(
            "/audit-logs/",
            params={"entity_type": "LeadComment", "entity_id": comment_id},
            headers=api.headers,
        )
        assert resp_audit.status_code == 200, resp_audit.text
        items = resp_audit.json().get("items", resp_audit.json())
        matching = [i for i in items if i["entity_type"] == "LeadComment" and i["entity_id"] == comment_id]
        assert len(matching) == 1, f"La fila de auditoría del comentario no aparece via API: {resp_audit.json()}"

    def test_audit_row_keeps_real_organization_id_when_object_has_one(
        self, api, db_session, initial_structure
    ):
        """Control: para un modelo que SÍ tiene organization_id propio (ej.
        Workspace), el fallback no debe pisar el valor real del objeto."""
        org_id = initial_structure["org_id"]

        resp = api.client.post(
            "/workspaces/",
            json={"name": "Workspace Auditado", "is_public": True},
            headers=api.headers,
        )
        assert resp.status_code in (200, 201), resp.text
        ws_id = resp.json()["id"]

        audit_row = (
            db_session.query(SystemAuditLog)
            .filter_by(entity_type="Workspace", entity_id=ws_id)
            .first()
        )
        assert audit_row is not None
        assert audit_row.organization_id == org_id


class TestAuditLogFallbackDoesNotCrashOnNonexistentOrg:
    """Regresión de la regresión: la primera versión del fix reventaba con
    IntegrityError si TENANT_ORG_ID apuntaba a una organización inexistente."""

    def test_create_organization_with_nonexistent_org_header_does_not_crash(self, api, db_session):
        """Reproduce el crash real detectado en producción: crear una
        organización nueva mientras el header X-Organization-Id trae un id
        que no existe. OrganizationController no exige que ese header sea
        válido para 'create' (ver auditoria.md §7 / usuarios_y_permisos.md),
        así que esto es una request legítima, no un ataque."""
        resp = api.client.post(
            "/organizations/",
            json={"name": "Org Con Header De Org Inexistente"},
            headers={"X-Organization-Id": "999999999"},
        )
        assert resp.status_code in (200, 201), resp.text
        new_org_id = resp.json()["id"]

        audit_row = (
            db_session.query(SystemAuditLog)
            .filter_by(entity_type="Organization", entity_id=new_org_id)
            .first()
        )
        assert audit_row is not None
        # Debe quedar asociada a la organización recién creada, no al header inexistente.
        assert audit_row.organization_id == new_org_id

    def test_log_audit_falls_back_to_null_when_tenant_org_id_does_not_exist(
        self, db_session, initial_structure, initial_fields, api
    ):
        """Nivel más bajo: si TENANT_ORG_ID apunta a una org inexistente y el
        modelo auditado no es Organization, _log_audit no debe reventar —
        debe caer a organization_id=NULL como comportamiento seguro."""
        lead = _create_lead(api, initial_structure["campaign_id"], initial_fields["nombre_id"])
        comment = LeadComment(lead_id=lead["id"], content="Comentario para test de bajo nivel")
        db_session.add(comment)
        db_session.flush()

        token = TENANT_ORG_ID.set(999999999)  # organización que no existe
        try:
            LeadCommentService._log_audit(db_session, comment, action="CREATED", changes=None, user_id=None)
            db_session.flush()  # si el fallback fuera inseguro, esto lanzaría IntegrityError
        finally:
            TENANT_ORG_ID.reset(token)

        audit_row = (
            db_session.query(SystemAuditLog)
            .filter_by(entity_type="LeadComment", entity_id=comment.id)
            .order_by(SystemAuditLog.id.desc())
            .first()
        )
        assert audit_row is not None
        assert audit_row.organization_id is None
