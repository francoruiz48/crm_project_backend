"""
test_storage_and_import_permissions.py
========================================
Cobertura del hallazgo #3 de la auditoría (2026-07-10): varios endpoints de
`storage_controller.py` e `import_export_controller.py` eran alcanzables sin
autenticación, o autenticados pero sin ningún chequeo de permiso específico.

Bugs corregidos (2026-07-10):
- `POST /storage/upload` no tenía ninguna dependencia de autenticación.
- `POST /import/detect-headers` no tenía ninguna dependencia de autenticación.
- `POST /import/process` exigía estar logueado, pero no un permiso específico
  (cualquier usuario autenticado de la organización podía crear leads vía
  importación, sin necesidad del permiso `lead:create`).
- `GET /export/{campaign_id}` exigía estar logueado, pero no un permiso
  específico (cualquier usuario autenticado podía exportar leads de cualquier
  campaña a la que tuviera acceso de lectura por tenant, sin el permiso
  `lead:view`).

Nota sobre `lead:view` vs `lead:view_all` en el fix de export: se usó
`lead:view` (no `lead:view_all`) a propósito. El rol "agent" (uso diario) solo
tiene `lead:view` — exigir `lead:view_all` le hubiera impedido exportar
incluso sus propios leads asignados. `lead:view` + el filtro de visibilidad
que ya aplica `LeadRepository.get_all` (ver `lead_repository.py`) es el mismo
patrón que usa `GET /leads/`.
"""
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.core.security import _get_current_user
from tests.fixtures.user_fixtures import (
    _apply_user_overrides,
    _link_user_to_org,
    _make_user,
    _remove_user_overrides,
)


def _dummy_excel() -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.append(["nombre", "apellido"])
    ws.append(["Juan", "Perez"])
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


class TestUnauthenticatedAccessBlocked:
    """Regresión: estos endpoints eran alcanzables sin ningún token."""

    def test_storage_upload_requires_authentication(self, api):
        app = api.client.app
        original = app.dependency_overrides.get(_get_current_user)
        app.dependency_overrides.pop(_get_current_user, None)
        try:
            resp = api.client.post(
                "/storage/upload",
                files={"file": ("test.txt", b"contenido", "text/plain")},
            )
            assert resp.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[_get_current_user] = original

    def test_import_detect_headers_requires_authentication(self, api):
        app = api.client.app
        original = app.dependency_overrides.get(_get_current_user)
        app.dependency_overrides.pop(_get_current_user, None)
        try:
            excel_file = _dummy_excel()
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            resp = api.client.post(
                "/import/detect-headers",
                files={"file": ("test.xlsx", excel_file, mime)},
            )
            assert resp.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[_get_current_user] = original


class TestImportExportPermissionChecks:
    """Regresión: estos endpoints exigían login pero no un permiso puntual."""

    def test_import_process_requires_lead_create_permission(self, client, db_session, initial_structure, api):
        """Un usuario 'viewer' (lead:view, lead:view_all, pero SIN lead:create)
        no debe poder importar leads."""
        from app.main import app

        org_id = initial_structure["org_id"]
        campaign_id = initial_structure["campaign_id"]
        viewer_user = _make_user(db_session, "Viewer Import", "viewer_import@test.com")
        _link_user_to_org(db_session, viewer_user, org_id, role_code="viewer")
        db_session.commit()

        _apply_user_overrides(app, viewer_user, org_id)
        try:
            excel_file = _dummy_excel()
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            resp = client.post(
                "/import/process",
                files={"file": ("test.xlsx", excel_file, mime)},
                data={"campaign_id": campaign_id, "mapping": "{}"},
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_export_requires_lead_view_permission(self, client, db_session, initial_structure, api):
        """Un usuario sin ningún rol asignado en la organización (sin permisos)
        no debe poder exportar leads."""
        from app.main import app

        org_id = initial_structure["org_id"]
        campaign_id = initial_structure["campaign_id"]
        no_perms_user = _make_user(db_session, "Sin Permisos", "sin_permisos_export@test.com")
        # role_code inexistente a propósito: el link queda sin roles -> permissions == []
        _link_user_to_org(db_session, no_perms_user, org_id, role_code="rol_inexistente")
        db_session.commit()

        _apply_user_overrides(app, no_perms_user, org_id)
        try:
            resp = client.get(
                f"/export/{campaign_id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_still_can_import_and_export(self, api, initial_structure):
        """Control: el superadmin (que ya lo hacía) sigue pudiendo usar ambos
        endpoints con normalidad después de agregar los PermissionChecker."""
        campaign_id = initial_structure["campaign_id"]

        excel_file = _dummy_excel()
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        resp_import = api.client.post(
            "/import/process",
            files={"file": ("test.xlsx", excel_file, mime)},
            data={"campaign_id": campaign_id, "mapping": "{}"},
            headers=api.headers,
        )
        assert resp_import.status_code != 403

        resp_export = api.client.get(f"/export/{campaign_id}", headers=api.headers)
        assert resp_export.status_code == 200
