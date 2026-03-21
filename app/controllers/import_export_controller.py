from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.lead_import_export_service import LeadImportExportService
from app.schemas.import_export_schema import ImportHeadersResponse, ImportResultResponse
from app.core.security import get_current_user # Asumo que tienes auth

router = APIRouter()

@router.post("/import/detect-headers", response_model=ImportHeadersResponse)
def detect_headers(file: UploadFile = File(...)):
    """
    Sube un Excel y devuelve la lista de encabezados detectados.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Formato de archivo inválido. Solo se permite Excel.")
        
    headers = LeadImportExportService.get_excel_headers(file)
    return {"headers": headers}

@router.post("/import/process", response_model=ImportResultResponse)
def process_import(
    campaign_id: int = Form(...),
    mapping: str = Form(..., description='JSON String: {"ColumnaExcel": "NombreCampoDB"}'),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
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
        user_id=current_user.id
    )

@router.get("/export/{campaign_id}")
def export_leads(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Descarga un Excel con todos los leads de la campaña.
    """
    excel_file = LeadImportExportService.export_leads(db, campaign_id, user_id=current_user.id)
    
    headers = {
        'Content-Disposition': f'attachment; filename="leads_campaign_{campaign_id}.xlsx"'
    }
    
    return StreamingResponse(
        excel_file, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        headers=headers
    )