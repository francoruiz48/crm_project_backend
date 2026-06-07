from typing import Optional, List
from fastapi import HTTPException, status
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from app.db.unit_of_work import UnitOfWork
from app.models.web_form import WebForm
from app.models.web_form_field import WebFormField
from app.models.lead_field import LeadField
from app.db.repository.web_form_repository import WebFormRepository
from app.db.repository.campaign_repository import CampaignRepository
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction

class WebFormService(BaseService):
    repository = WebFormRepository
    campaign_repository = CampaignRepository

    # =========================================================================
    # HELPERS DE SEGURIDAD
    # =========================================================================

    @classmethod
    def _validate_form_fields(cls, session, campaign_id: int, fields_in: list):
        """
        Garantiza que todos los lead_field_id provistos existan, 
        pertenezcan a la campaña correcta y estén activos.
        """
        if not fields_in:
            return

        lead_field_ids = [f.lead_field_id for f in fields_in]
        
        # 1. Prevenir duplicados en el mismo payload
        if len(lead_field_ids) != len(set(lead_field_ids)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                detail=[{"field": "fields", "message": "No puede agregar el mismo campo más de una vez al formulario."}]
            )

        # 2. Buscar los campos reales en la BD
        db_fields = session.query(LeadField).filter(LeadField.id.in_(lead_field_ids)).all()

        if len(db_fields) != len(lead_field_ids):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                detail=[{"field": "fields", "message": "Uno o más campos especificados no existen en el sistema."}]
            )

        # 3. Validación cruzada de Campaña y Estado (Anti-IDOR)
        for db_f in db_fields:
            if db_f.campaign_id != campaign_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "fields", "message": f"El campo '{db_f.name}' pertenece a otra campaña. Operación rechazada."}]
                )
            if not db_f.active:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "fields", "message": f"El campo '{db_f.name}' está inactivo y no puede usarse en formularios web."}]
                )

    # =========================================================================
    # METODOS CRUD (Área Privada)
    # =========================================================================

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            data = obj_in.model_dump(exclude_unset=True)
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()
            
            # Extraemos los campos hijos antes de crear el padre
            fields_in = data.pop("fields", [])
            campaign_id = data.get("campaign_id")

            # 1. Validar propiedad de la campaña (Asegura que no asigne a campaña ajena)
            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_id, user_context=user_context)
            if not campaign:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "campaign_id", "message": "La campaña no existe o no pertenece a su organización."}]
                )

            # Inyectamos el org_id en el payload del formulario por seguridad
            data["organization_id"] = org_id

            # 2. Validar blindaje de campos hijos
            cls._validate_form_fields(uow.session, campaign_id, obj_in.fields)

            # 3. Crear el Formulario (Padre)
            new_form = cls.repository.create(uow.session, data, user_context=user_context)
            uow.session.flush() # Obligatorio para obtener new_form.id

            # 4. Crear los Campos (Hijos)
            for field_data in fields_in:
                new_field = WebFormField(
                    web_form_id=new_form.id,
                    **field_data
                )
                uow.session.add(new_field)

            # 5. Auditoría
            cls._log_audit(uow.session, new_form, action=SystemAuditLogAction.CREATED, changes=data, user_id=user_context.user.id if user_context else None)
            
            return new_form

        return cls._execute(action="Crear WebForm", func=do_create)


    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()
            
            # 1. 🛡️ SEGURIDAD ESTRICTA: Asegurarnos que el formulario es de la organización
            current_form = uow.session.query(WebForm).filter(
                WebForm.id == obj_id,
                WebForm.organization_id == org_id
            ).first()
            
            if not current_form: 
                cls._not_found(obj_id)

            data = obj_in.model_dump(exclude_unset=True)
            fields_in = data.pop("fields", None)

            # 2. Reemplazo Total de Campos
            if fields_in is not None:
                # Validamos seguridad de los campos entrantes
                cls._validate_form_fields(uow.session, current_form.campaign_id, obj_in.fields)
                
                # Borramos TODOS los campos actuales (SQL Bulk Delete)
                uow.session.query(WebFormField).filter(WebFormField.web_form_id == obj_id).delete(synchronize_session=False)
                
                # Insertamos los nuevos
                for f_data in fields_in:
                    new_field = WebFormField(
                        web_form_id=obj_id,
                        **f_data
                    )
                    uow.session.add(new_field)

            # 3. Actualizamos los datos base del formulario
            if data:
                cls.repository.update(uow.session, obj_id, data, user_context=user_context)

            uow.session.flush() # Sincroniza el borrado e insertado en la transacción
            
            # Retornamos detailed=True para que el frontend reciba la nueva estructura
            return cls.repository.get_by_id(uow.session, obj_id, user_context=user_context, detailed=True)

        return cls._execute(action="Actualizar WebForm", obj_id=obj_id, func=do_update)


    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_delete(uow):
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()
            
            # 1. 🛡️ SEGURIDAD ESTRICTA: Asegurar que el borrado sea del dueño
            current_form = uow.session.query(WebForm).filter(
                WebForm.id == obj_id,
                WebForm.organization_id == org_id
            ).first()

            if not current_form: 
                cls._not_found(obj_id)

            # Delegamos al repositorio la eliminación real/soft-delete
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            
            cls._log_audit(uow.session, current_form, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_context.user.id if user_context else None)
            return result

        return cls._execute(action="Eliminar WebForm", obj_id=obj_id, func=do_delete)

    # =========================================================================
    # METODOS PÚBLICOS (Área Expuesta a Internet)
    # =========================================================================

    @classmethod
    def get_public_form_by_uuid(cls, uuid: str):
        """
        Obtiene un formulario mediante su UUID público.
        Este método NO recibe user_context porque es consumido sin token.
        """
        def do_get(uow):
            form = uow.session.query(WebForm).filter_by(public_uuid=uuid, active=True).first()
            if not form:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, 
                    detail=[{"field": "general", "message": "El formulario no existe o fue desactivado."}]
                )
            
            # Verificamos que la organización y la campaña sigan activas
            if not form.organization.active or not form.campaign.active:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, 
                    detail=[{"field": "general", "message": "Este formulario ya no está disponible."}]
                )

            return form

        return cls._execute(action="Obtener Formulario Público", func=do_get)