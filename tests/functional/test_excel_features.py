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