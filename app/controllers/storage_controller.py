from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from app.controllers.base_controller import BaseController
from app.services.storage_service import StorageService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.core.security import get_current_user

router = APIRouter(prefix="/storage")

@router.post("/upload")
def upload_file(
    file: UploadFile = File(...)
):
    # 3. Subir a Supabase
    path = StorageService.upload_file(file)
    
    public_url = StorageService.get_public_url(path)
    
    return {
        "path": path,
        "url": public_url
    }