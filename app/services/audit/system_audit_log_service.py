from typing import Optional
from app.core.constans import DEFAULT_PAGE_SIZE
from app.core.security import UserContext
from app.services.base_service import BaseService
from app.db.repository.audit.system_audit_log_repository import SystemAuditLogRepository

class SystemAuditLogService(BaseService):
    repository = SystemAuditLogRepository

    @classmethod
    def get_all(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                only_active: bool = True, detailed: bool = False, search: str = None, **kwargs):
        """El front filtra por `entity_id` mandando el uuid real de la entidad auditada
        (nunca conoce el id interno). `entity_id` sigue siendo la columna Integer interna
        en el modelo -- el filtro genérico de BaseRepository.get_all() la compararía tal
        cual contra el uuid recibido y rompería (Integer vs texto en Postgres). Acá se
        traduce antes de bajar al repo: si el valor no es numérico, se filtra por la
        columna nueva `entity_uuid` en su lugar; si es numérico, se deja pasar como
        `entity_id` (compatibilidad con uso interno). Ver backend/AGENTS.md §18-ter."""
        entity_id_filter = kwargs.pop("entity_id", None)
        if entity_id_filter is not None:
            is_numeric = isinstance(entity_id_filter, int) or (
                isinstance(entity_id_filter, str) and entity_id_filter.lstrip("-").isdigit()
            )
            if is_numeric:
                kwargs["entity_id"] = entity_id_filter
            else:
                kwargs["entity_uuid"] = entity_id_filter

        return super().get_all(
            user_context=user_context, page=page, page_size=page_size,
            only_active=only_active, detailed=detailed, search=search, **kwargs
        )

    @classmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def update(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def delete(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")