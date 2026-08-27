from fastapi import APIRouter, Depends, UploadFile, File
from app.services.storage_service import StorageService
from app.core.security import get_current_user_roles

router = APIRouter(prefix="/storage")

@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    user_context = Depends(get_current_user_roles)
):
    # 3. Subir a Supabase
    path = StorageService.upload_file(file)
    
    public_url = StorageService.get_public_url(path)
    
    return {
        "path": path,
        "url": public_url
    }

