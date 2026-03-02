import uuid
from supabase import create_client, Client
from fastapi import UploadFile, HTTPException
from app.core.config import settings
from app.core.constans import ALLOWED_IMAGE_TYPES, ALLOWED_DOCUMENT_TYPES, MAX_FILE_SIZE_MB

class StorageService:
    _client: Client = None

    @classmethod
    def get_client(cls) -> Client:
        if not cls._client:
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client

    @classmethod
    def validate_file(cls, file: UploadFile, allowed_types: list):
        
        """Valida tamaño y tipo MIME"""
        # 1. Validar Tipo
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Tipo de archivo no permitido: {file.content_type}. Esperado: {allowed_types}"
            )
        
        # 2. Validar Tamaño (Opcional, requiere leer el archivo o usar headers)
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(400, f"El archivo excede los {MAX_FILE_SIZE_MB}MB")
        
    @classmethod
    def upload_file(cls, file: UploadFile, folder: str = "uploads") -> str:
        client = cls.get_client()
        
        # Sanitizar nombre
        file_ext = file.filename.split(".")[-1]
        unique_name = f"{uuid.uuid4()}.{file_ext}"
        path = f"{folder}/{unique_name}"
        
        try:
            file.file.seek(0)
            file_content = file.file.read()
            client.storage.from_(settings.SUPABASE_BUCKET).upload(
                path=path,
                file=file_content,
                file_options={"content-type": file.content_type}
            )
            return path
        except Exception as e:
            raise HTTPException(500, detail=f"Error subiendo archivo a Supabase: {str(e)}")

    @classmethod
    def get_public_url(cls, path: str) -> str:
        # Si el path es nulo o vacío, devolver None
        if not path: return None
        # Si ya es una URL completa (migración antigua), devolverla
        if path.startswith("http"): return path
        
        client = cls.get_client()
        return client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)