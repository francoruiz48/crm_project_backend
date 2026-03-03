from fastapi import Depends, HTTPException, status, Header
from app.db.session import SessionLocal, get_db
from app.models.security_models import User
from app.core.context import TENANT_ORG_ID

# --- MOCK AUTHENTICATION ---
def get_current_user(db = Depends(get_db)) -> User:
    user_id_to_simulate = 1
    
    user = db.get(User, user_id_to_simulate)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario simulado no encontrado (corre los seeders)")
    return user


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self, 
        user: User = Depends(get_current_user), 
        # Exigimos el ID de la organización desde el Header
        x_organization_id: int = Header(default=None, alias="X-Organization-Id")
    ):
        
        # GUARDAMOS EL ID EN EL CONTEXTO GLOBAL DE LA PETICIÓN
        if x_organization_id:
            TENANT_ORG_ID.set(x_organization_id)
            
        # 1. Si es superadmin global, tiene acceso a todo (opcional según tus reglas)
        if user.is_superuser:
            return True

        # 2. Verificar que mandaron el contexto de la empresa
        if not x_organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falta el header 'X-Organization-Id' para verificar los permisos en este contexto."
            )

        # 3. Obtenemos la lista de permisos en ESA organización específica
        user_permissions = user.get_permissions(org_id=x_organization_id)

        # 4. Validar
        if self.required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos en esta organización. Requiere: {self.required_permission}"
            )
        
        return True