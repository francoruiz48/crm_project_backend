import uuid
import os
from supabase import create_client, Client
from fastapi import UploadFile, HTTPException
from app.core.config import settings

class StorageService:
    _client: Client = None

    @classmethod
    def get_client(cls) -> Client:
        if not cls._client:
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client

    @classmethod
    def upload_file(cls, file: UploadFile, folder: str = "uploads") -> str:
        """
        Sube archivo a Supabase y retorna el Path relativo.
        """
        client = cls.get_client()
        
        # Generar nombre único: uploads/uuid-nombre_original
        file_ext = file.filename.split(".")[-1]
        unique_name = f"{uuid.uuid4()}.{file_ext}"
        path = f"{folder}/{unique_name}"
        
        try:
            file_content = file.file.read()
            # Subir a Supabase
            res = client.storage.from_(settings.SUPABASE_BUCKET).upload(
                path=path,
                file=file_content,
                file_options={"content-type": file.content_type}
            )
            # Retornamos el path para guardarlo en la BD
            return path
        except Exception as e:
            raise HTTPException(500, detail=f"Error subiendo archivo a Supabase: {str(e)}")

    @classmethod
    def get_public_url(cls, path: str) -> str:
        client = cls.get_client()
        return client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)