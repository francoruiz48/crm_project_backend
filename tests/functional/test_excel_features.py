import pytest
from io import BytesIO
import json
from openpyxl import Workbook

# --- Helper Local ---
def create_dummy_excel():
    """Crea un archivo Excel binario válido en memoria"""
    wb = Workbook()
    ws = wb.active
    ws.append(["nombre", "apellido", "email"])
    ws.append(["Juan", "Perez", "juan@test.com"])
    
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out

# --- Tests ---

def test_export_campaign_data(api, initial_structure):
    """Prueba la descarga de datos (Export)"""
    camp_id = initial_structure["campaign_id"]

    # Intenta rutas comunes, ajusta según tu router real
    resp = api.client.get(f"/export/{camp_id}", headers=api.headers)

    if resp.status_code == 404:
        resp = api.client.get(f"/leads/export/{camp_id}", headers=api.headers)

    assert resp.status_code in [200, 201, 202], f"Fallo Export: {resp.text}"
    # Validar que sea un archivo (binario o text)
    assert len(resp.content) > 0

def test_export_campaign_data_includes_field_values(api, initial_fields):
    """
    Regresión del bug real encontrado 2026-08-01 (ver backend/AGENTS.md §51):
    export_leads() armaba field_map con .id de LeadFieldRepository.get_all() (public_uuid,
    Fase 3), pero lo buscaba con fv.field_id (id interno crudo, Fase 4 sin migrar) -- nunca
    matcheaba, así que el Excel exportado tenía las columnas correctas pero TODAS las celdas
    vacías. test_export_campaign_data (arriba) no lo detectaba porque solo valida status code
    y que el archivo no esté vacío -- un Excel de solo encabezados también pasa esa prueba.
    Acá se crea un lead con un valor real y se verifica que ese valor efectivamente aparezca
    en la celda correspondiente del archivo exportado.
    """
    import pandas as pd
    from io import BytesIO

    camp_id = initial_fields["campaign_id"]
    field_nombre_id = initial_fields["nombre_id"]

    values = [{"field_id": field_nombre_id, "value": "Carlos Exportado"}]
    api.create_lead(campaign_id=camp_id, values=values, expected_status=200)

    resp = api.client.get(f"/export/{camp_id}", headers=api.headers)
    assert resp.status_code == 200, f"Fallo Export: {resp.text}"

    df = pd.read_excel(BytesIO(resp.content), sheet_name="Leads")
    assert "Nombre" in df.columns, f"Falta la columna 'Nombre' en el export: {df.columns.tolist()}"
    assert "Carlos Exportado" in df["Nombre"].values, \
        f"El valor del lead no aparece en la columna exportada (celdas vacías): {df['Nombre'].tolist()}"

def test_import_detect_headers(api):
    """Prueba que el backend pueda leer las cabeceras de un Excel"""
    excel_file = create_dummy_excel()
    mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    
    files = {'file': ('test.xlsx', excel_file, mime)}
    
    resp = api.client.post("/import/detect-headers", files=files, headers=api.headers)
    assert resp.status_code == 200, f"Fallo Detect Headers: {resp.text}"
    
    data = resp.json()
    # Debe devolver lista o dict con key 'headers'
    assert isinstance(data, list) or "headers" in data

def test_import_process_file(api, initial_structure):
    """Prueba el proceso completo de importación con mapeo"""
    camp_id = initial_structure["campaign_id"]
    excel_file = create_dummy_excel()
    mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    
    files = {'file': ('import_test.xlsx', excel_file, mime)}
    data = {
        "campaign_id": camp_id,
        "mapping": json.dumps({"0": "nombre", "1": "apellido"}) # Mapeo dummy
    }
    
    # Ajusta la ruta si es /import_leads o /import/process
    resp = api.client.post("/import/process", files=files, data=data, headers=api.headers)

    # Aceptamos 200/201 (Ok) o 422/400 (Validación lógica), pero NO 500
    assert resp.status_code != 500, f"Error Interno en Import: {resp.text}"
    assert resp.status_code in [200, 201, 400, 422]

def test_import_process_resolves_related_lead_field(api, db_session, initial_structure):
    """
    Regresión del bug real encontrado 2026-08-01 (ver backend/AGENTS.md §51):
    _resolve_related_leads() armaba target_fields con LeadFieldRepository.get_all()
    (schemas Pydantic, cuyo .id es el public_uuid del campo, Fase 3), y usaba ese .id
    directo en un filtro raw contra LeadFieldValue.field_id (columna int real, Fase 4
    deliberadamente sin migrar) -- nunca podía matchear, así que importar una columna de
    tipo "Lead relacionado" siempre fallaba con "No se encontró el lead relacionado...".
    """
    from app.models.lead_field import LeadField
    from app.models.lead_state import LeadState
    from app.models.campaign import Campaign
    from app.models.workspace import Workspace
    from app.models.lead_flow import LeadFlow
    from app.models.lead_field_section import LeadFieldSection
    from openpyxl import Workbook

    org_id = initial_structure["org_id"]
    ws_internal_id = db_session.query(Workspace.id).filter_by(public_uuid=initial_structure["workspace_id"]).scalar()
    lead_flow_internal_id = db_session.query(LeadFlow.id).filter_by(public_uuid=initial_structure["lead_flow_id"]).scalar()
    section_internal_id = db_session.query(LeadFieldSection.id).filter_by(public_uuid=initial_structure["section_id"]).scalar()
    camp_source_id = initial_structure["campaign_id"]

    # Campaña destino, con un campo primario (se usa para ubicar el lead por su valor).
    camp_target = Campaign(name="Destino Import", workspace_id=ws_internal_id, lead_flow_id=lead_flow_internal_id, organization_id=org_id)
    db_session.add(camp_target)
    db_session.flush()
    state_target = LeadState(lead_flow_id=lead_flow_internal_id, organization_id=org_id, name="Nuevo", category="OPEN", is_initial=True, order=1)
    db_session.add(state_target)
    db_session.commit()

    f_target_code = LeadField(
        name="Codigo", field_type_code="STRING", campaign_id=camp_target.id, order=1,
        lead_field_section_id=section_internal_id, organization_id=org_id, active=True, is_primary=True
    )
    db_session.add(f_target_code)
    db_session.commit()

    api.create_lead(
        campaign_id=camp_target.public_uuid,
        values=[{"field_id": f_target_code.id, "value": "REF-001"}],
        expected_status=200
    )

    # Campo relacional en la campaña origen, apuntando a la campaña destino.
    res_field = api.client.post("/lead_fields/", json={
        "name": "Lead Relacionado",
        "field_type_code": "LEAD",
        "campaign_id": camp_source_id,
        "related_campaign_id": camp_target.public_uuid,
        "order": 10
    }, headers=api.headers)
    assert res_field.status_code == 200, res_field.text

    wb = Workbook()
    ws = wb.active
    ws.append(["Codigo"])
    ws.append(["REF-001"])
    out = BytesIO()
    wb.save(out)
    out.seek(0)

    files = {'file': ('import_rel.xlsx', out, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    data = {
        "campaign_id": camp_source_id,
        "mapping": json.dumps({"Codigo": "Lead Relacionado.Codigo"})
    }
    resp = api.client.post("/import/process", files=files, data=data, headers=api.headers)
    assert resp.status_code == 200, f"Fallo Import: {resp.text}"

    result = resp.json()
    assert result["imported"] == 1, f"No se resolvió el lead relacionado: {result}"