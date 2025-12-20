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
    """
    ESTO ES UN MOCK.
    En el futuro, aquí leerás el JWT del header Authorization, 
    decodificarás el ID y buscarás al usuario.
    
    POR AHORA: Retorna siempre al usuario con ID 1 (El Super Admin)
    o el ID 2 (El Vendedor) según con quién quieras probar.
    """
    user_id_to_simulate = 1  # <--- CAMBIA ESTO PARA PROBAR DIFERENTES ROLES
    
    user = db.query(User).get(user_id_to_simulate)
    if not user:
        # Si no has corrido los seeders, esto fallará
        raise HTTPException(status_code=404, detail="Usuario simulado no encontrado (corre los seeders)")
    return user

# --- EL GUARDIÁN DE PERMISOS ---
class PermissionChecker:
    """
    Clase invocable para usar como dependencia parametrizada.
    Uso: Depends(PermissionChecker("lead:create"))
    """
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: User = Depends(get_current_user)):
        # 1. Obtenemos los permisos del rol del usuario
        if not user.role:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El usuario no tiene un rol asignado."
            )

        # 2. Verificamos si tiene el permiso exacto
        # (Optimizaremos esto cargando los permisos en una lista simple)
        user_permissions = [p.codename for p in user.role.permissions]

        if self.required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos para realizar esta acción. Requiere: {self.required_permission}"
            )
        
        return True