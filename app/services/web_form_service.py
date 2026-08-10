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
    def _resolve_lead_field_ids(cls, session, fields_in: list):
        """
        fields_in[].lead_field_id llega como public_uuid del LeadField -- este módulo entero
        nunca había pasado por la migración a uuid (Fase 3/4, ver backend/AGENTS.md), a
        diferencia de prácticamente todo el resto del sistema. El frontend/test manda el uuid
        que devuelve POST /lead_fields/, pero el schema (WebFormFieldBase.lead_field_id) seguía
        siendo `int` y _validate_form_fields comparaba directo contra LeadField.id (int) -- 422
        en cualquier alta/edición de WebForm con campos (ver backend/AGENTS.md §18-undecies). Se
        resuelve acá, mutando cada item en el lugar (dict o Pydantic, mismo patrón que
        LeadService._resolve_value_field_ids), ANTES de _validate_form_fields y del dump que
        arma los WebFormField reales -- así el resto de esta clase sigue comparando ids internos.
        """
        if not fields_in:
            return fields_in
        from app.db.repository.lead_field_repository import LeadFieldRepository
        for f in fields_in:
            is_dict = isinstance(f, dict)
            raw_fid = f.get('lead_field_id') if is_dict else getattr(f, 'lead_field_id', None)
            if raw_fid is None:
                continue
            if isinstance(raw_fid, int) or (isinstance(raw_fid, str) and raw_fid.lstrip('-').isdigit()):
                resolved = int(raw_fid)
            else:
                resolved = LeadFieldRepository.get_internal_id_by_public_uuid(session, raw_fid)
                if resolved is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "fields", "message": f"El campo '{raw_fid}' no existe en el sistema."}]
                    )
            if is_dict:
                f['lead_field_id'] = resolved
            else:
                f.lead_field_id = resolved
        return fields_in

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
            # obj_in.campaign_id llega como public_uuid (Fase 3, nunca migrado en este módulo --
            # ver backend/AGENTS.md §18-undecies). Se resuelve al id interno en una variable
            # aparte -- NO se reasigna a obj_in.campaign_id (tipado `str` en WebFormCreate):
            # hacerlo ahí disparaba un warning de serialización de Pydantic
            # (PydanticSerializationUnexpectedValue) al llamar obj_in.model_dump() un par de
            # líneas más abajo, porque el campo queda con un `int` donde el schema espera `str`
            # (mismo patrón de bug ya documentado para LeadRoutingConditionCreate.lead_field_id,
            # ver backend/AGENTS.md §21/§53). None si no existe -- el chequeo `if not campaign`
            # de abajo ya cubre ese caso con el mensaje correcto.
            campaign_internal_id = cls.campaign_repository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)
            # Mismo motivo para obj_in.fields[].lead_field_id (ver _resolve_lead_field_ids) --
            # ese caso no dispara el warning porque WebFormFieldCreate.lead_field_id ya está
            # tipado Union[int, str], así que sí se puede mutar in-place sin problema.
            cls._resolve_lead_field_ids(uow.session, obj_in.fields)

            data = obj_in.model_dump(exclude_unset=True)
            data["campaign_id"] = campaign_internal_id
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()

            # Extraemos los campos hijos antes de crear el padre
            fields_in = data.pop("fields", [])
            campaign_id = data.get("campaign_id")

            # 1. Validar propiedad de la campaña (Asegura que no asigne a campaña ajena)
            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_id, user_context=user_context) if campaign_id is not None else None
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

            # new_form.id es el public_uuid (repository.create() devuelve el schema Pydantic, no
            # el ORM crudo) -- se resuelve acá al id interno antes de usarlo como FK real. Bug
            # real encontrado 2026-07-28 (mismo patrón que en los demás services): rompía la
            # creación de un WebForm con campos hijos.
            new_form_internal_id = cls.repository.get_internal_id_by_public_uuid(uow.session, new_form.id)

            # 4. Crear los Campos (Hijos)
            for field_data in fields_in:
                new_field = WebFormField(
                    web_form_id=new_form_internal_id,
                    **field_data
                )
                uow.session.add(new_field)

            # 5. Auditoría
            cls._log_audit(uow.session, new_form, action=SystemAuditLogAction.CREATED, changes=data, user_id=user_context.user.id if user_context else None)
            
            return new_form

        return cls._execute(action="Crear WebForm", func=do_create)


    @classmethod
    def update(cls, obj_id: str, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()

            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # 1. 🛡️ SEGURIDAD ESTRICTA: Asegurarnos que el formulario es de la organización
            current_form = uow.session.query(WebForm).filter(
                WebForm.id == internal_id,
                WebForm.organization_id == org_id
            ).first()

            if not current_form:
                cls._not_found(obj_id)

            # obj_in.fields[].lead_field_id llega como public_uuid del LeadField (ver
            # _resolve_lead_field_ids) -- se resuelve ANTES del dump, mismo motivo que en create().
            if obj_in.fields is not None:
                cls._resolve_lead_field_ids(uow.session, obj_in.fields)

            data = obj_in.model_dump(exclude_unset=True)
            fields_in = data.pop("fields", None)

            # 2. Reemplazo Total de Campos
            if fields_in is not None:
                # Validamos seguridad de los campos entrantes
                cls._validate_form_fields(uow.session, current_form.campaign_id, obj_in.fields)

                # Borramos TODOS los campos actuales (SQL Bulk Delete)
                uow.session.query(WebFormField).filter(WebFormField.web_form_id == internal_id).delete(synchronize_session=False)

                # Insertamos los nuevos
                for f_data in fields_in:
                    new_field = WebFormField(
                        web_form_id=internal_id,
                        **f_data
                    )
                    uow.session.add(new_field)

            # 3. Actualizamos los datos base del formulario
            if data:
                cls.repository.update(uow.session, internal_id, data, user_context=user_context)

            uow.session.flush() # Sincroniza el borrado e insertado en la transacción

            # Retornamos detailed=True para que el frontend reciba la nueva estructura
            return cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)

        return cls._execute(action="Actualizar WebForm", obj_id=obj_id, func=do_update)


    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()

            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # 1. 🛡️ SEGURIDAD ESTRICTA: Asegurar que el borrado sea del dueño
            current_form = uow.session.query(WebForm).filter(
                WebForm.id == internal_id,
                WebForm.organization_id == org_id
            ).first()

            if not current_form:
                cls._not_found(obj_id)

            # Delegamos al repositorio la eliminación real/soft-delete
            result = cls.repository.delete(uow.session, internal_id, user_context=user_context)
            
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