from fastapi import Depends, HTTPException, status
from app.db.session import SessionLocal
from app.models.security_models import User
# from app.db.unit_of_work import UnitOfWork # Si prefieres usar UoW

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- MOCK AUTHENTICATION ---
def get_current_user(db = Depends(get_db)) -> User:
    user_id_to_simulate = 1  # <--- CAMBIAR ESTO PARA PROBAR DIFERENTES ROLES
    
    user = db.query(User).get(user_id_to_simulate)
    if not user:
        # Si no has corrido los seeders, esto fallará
        raise HTTPException(status_code=404, detail="Usuario simulado no encontrado (corre los seeders)")
    return user

class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: User = Depends(get_current_user)):
        # 1. Validar que el usuario tenga AL MENOS un rol
        if not user.roles:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El usuario no tiene roles asignados."
            )

        # 2. Obtenemos la lista combinada de permisos (gracias al helper actualizado)
        user_permissions = user.permission_codenames

        if self.required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos. Requiere: {self.required_permission}"
            )
        
        return True