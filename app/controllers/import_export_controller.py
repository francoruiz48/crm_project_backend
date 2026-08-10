from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.lead_import_export_service import LeadImportExportService
from app.schemas.import_export_schema import ImportHeadersResponse, ImportResultResponse
from app.core.security import get_current_user_roles, PermissionChecker

router = APIRouter()

@router.post("/import/detect-headers", response_model=ImportHeadersResponse)
def detect_headers(file: UploadFile = File(...), user_context = Depends(get_current_user_roles)):
    """
    Sube un Excel y devuelve la lista de encabezados detectados.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Formato de archivo inválido. Solo se permite Excel.")
        
    headers = LeadImportExportService.get_excel_headers(file)
    return {"headers": headers}

@router.post(
    "/import/process",
    response_model=ImportResultResponse,
    dependencies=[Depends(PermissionChecker("lead:create"))],
)
def process_import(
    # public_uuid de Campaign (Fase 3, ver backend/AGENTS.md §18); el service lo resuelve.
    campaign_id: str = Form(...),
    mapping: str = Form(..., description='JSON String: {"ColumnaExcel": "NombreCampoDB"}'),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_context = Depends(get_current_user_roles)
):
    """
    Importa leads a una campaña.
    Recibe el archivo y un JSON string con el mapeo.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Formato de archivo inválido.")

    return LeadImportExportService.import_leads(
        db=db, 
        file=file, 
        mapping_json=mapping, 
        campaign_id=campaign_id,
        user_context=user_context
    )

@router.get(
    "/export/{campaign_id}",
    dependencies=[Depends(PermissionChecker("lead:view"))],
)
def export_leads(
    # public_uuid de Campaign (Fase 3, ver backend/AGENTS.md §18); el service lo resuelve.
    campaign_id: str,
    db: Session = Depends(get_db),
    user_context = Depends(get_current_user_roles)
):
    """
    Descarga un Excel con todos los leads de la campaña.
    """
    file_bytes, campaign_name = LeadImportExportService.export_leads(db, campaign_id, user_context)

    filename = f"leads_{campaign_name}.xlsx"

    print("Exportando leads, nombre del archivo:", filename)
    
    return StreamingResponse(
        file_bytes, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )