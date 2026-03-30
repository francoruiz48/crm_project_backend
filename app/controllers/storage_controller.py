from fastapi import APIRouter, UploadFile, File
from app.services.storage_service import StorageService

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

