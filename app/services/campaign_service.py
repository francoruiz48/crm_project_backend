from typing import Optional
from fastapi import status, HTTPException
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.db.unit_of_work import UnitOfWork
from app.models.lead_flow import LeadFlow
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.core.security import UserContext
from app.models.lead import Lead
from app.schemas.lead_field_schema import LeadFieldCreate
from app.services.lead_field_service import LeadFieldService
from app.core.constans import SystemAuditLogAction

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository
    lead_flow_repository = LeadFlowRepository
    lead_field_service = LeadFieldService

    @classmethod
    def _create_default_fields(cls, uow, target_audience: str, campaign_id: int, user_context: UserContext):
        # 3. LÓGICA DE TEMPLATES B2B vs B2C
        default_fields = []
        
        if target_audience == "B2B":
            # Campos para Venta a Empresas
            default_fields = [
                {"name": "Nombre", "field_type_code": "STRING", "required": True, "is_primary": False, "order": 1, "title_order": 1},
                {"name": "Razón Social", "field_type_code": "STRING", "required": True, "is_primary": False, "order": 2},
                {"name": "Teléfono", "field_type_code": "STRING", "field_subtype_code": "PHONE", "required": False, "order": 3},
                {"name": "Email", "field_type_code": "STRING", "field_subtype_code": "EMAIL", "required": False, "order": 4},
                {"name": "Sitio Web", "field_type_code": "STRING", "field_subtype_code": "WEBSITE", "required": False, "order": 5},
            ]
        elif target_audience == "B2C":
                # Campos para Venta a Personas
                default_fields = [
                    {"name": "Nombre Completo", "field_type_code": "STRING", "required": True, "is_primary": False, "order": 1, "title_order": 1},
                    {"name": "Email", "field_type_code": "STRING", "field_subtype_code": "EMAIL", "required": False, "order": 2},
                    {"name": "Celular", "field_type_code": "STRING", "field_subtype_code": "MOBILE", "required": False, "order": 3},
                    {"name": "Fecha de Nacimiento", "field_type_code": "DATE", "field_subtype_code": "BIRTH_DATE", "required": False, "order": 4}
                ]

        for field_data in default_fields:
            field_data["campaign_id"] = campaign_id
            schema_in = LeadFieldCreate(**field_data)
            
            cls.lead_field_service.create_within_session(
                session=uow.session, 
                obj_in=schema_in, 
                user_context=user_context
            )

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        
        def do_create(uow):
            errors = []
            target_lead_flow_id = obj_in.lead_flow_id

            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id, user_context=user_context)
            if not workspace:
                errors.append({"field": "workspace_id", "message": "El espacio de trabajo especificado no existe."})
            else:
                # Validación de nombre único (activas e inactivas para no chocar con UniqueConstraint)
                existing = cls.repository.get_all(
                    session=uow.session,
                    name=obj_in.name,
                    workspace_id=obj_in.workspace_id,
                    only_active=False,
                    user_context=user_context
                )
                if existing:
                    active_ones = [e for e in existing if e.active]
                    if active_ones:
                        errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
                    else:
                        errors.append({"field": "name", "message": f"Ya existe una campaña desactivada llamada '{obj_in.name}' en este espacio de trabajo. Reactívela o use otro nombre."})

                # Validación/resolución del lead_flow_id (requiere workspace para obtener org)
                if not target_lead_flow_id:
                    # Si no envía ID, buscamos el flujo predeterminado (el más antiguo de la org)
                    default_flow = uow.session.query(LeadFlow).filter_by(
                        organization_id=workspace.organization_id
                    ).order_by(LeadFlow.created_at.asc()).first()

                    if not default_flow:
                        errors.append({"field": "lead_flow_id", "message": "La organización no tiene flujos de leads. Especifique uno manualmente."})
                    else:
                        target_lead_flow_id = default_flow.id
                else:
                    # Si envía ID, validamos que exista y pertenezca a su org
                    lead_flow = cls.lead_flow_repository.get_by_id(uow.session, target_lead_flow_id, user_context=user_context)
                    if not lead_flow:
                        errors.append({"field": "lead_flow_id", "message": "El flujo de leads especificado no existe."})
                    elif lead_flow.organization_id != workspace.organization_id:
                        errors.append({"field": "lead_flow_id", "message": "El flujo de leads no pertenece a la misma organización."})

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump(exclude={"lead_flow_id"}) 
            data["lead_flow_id"] = target_lead_flow_id

            target_audience = data.pop("target_audience", None)

            # 1. Crear la campaña base
            new_campaign = cls.repository.create(uow.session, data, user_context=user_context)
            
            # 2. Flush para que la BD le asigne un ID a new_campaign (necesario para el log)
            uow.session.flush() 

            cls._create_default_fields(uow, target_audience, new_campaign.id, user_context)

            # 3. LOG DE AUDITORÍA (Llamamos al helper del BaseService)
            cls._log_audit(
                session=uow.session,
                obj=new_campaign,
                action=SystemAuditLogAction.CREATED,
                changes=data,
                user_id=user_context.user.id if user_context and user_context.user else None
            )

            return new_campaign

        return cls._execute(action="Crear Campaña", func=do_create)
    
    @classmethod
    def _assert_can_modify_campaign(cls, campaign, user_context: Optional[UserContext] = None, action_label: str = "editar"):
        """SEGURIDAD: Solo el creador, el owner de la organización o un superadmin
        pueden modificar una campaña — aunque el usuario tenga el permiso RBAC
        genérico (campaign:update/delete) vía su rol. Es una capa extra encima
        del RBAC estándar, específica de este servicio.

        Hallazgo #19 (2026-07-11): esta regla ya era intencional en update() (con
        test dedicado), pero delete()/deactivate() no la tenían — un admin
        no-creador no podía renombrar una campaña ajena, pero sí borrarla del
        todo (incluso hard-delete con cascada vía ?force=true). Se extrajo acá
        para reusarla en los tres métodos. Confirmado con el usuario: "admin"
        significa superadmin global (is_superuser), no el rol admin de la
        organización — no se agregó ninguna condición nueva, solo se replicó
        la regla existente."""
        if user_context and user_context.user:
            is_superuser = getattr(user_context, 'is_superuser', False)
            is_owner = getattr(user_context, 'is_owner', False)
            is_creator = campaign.created_by == user_context.user.id
            if not (is_superuser or is_owner or is_creator):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"No tenés permiso para {action_label} esta campaña."
                )

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            campaign = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not campaign:
                cls._not_found(obj_id)

            cls._assert_can_modify_campaign(campaign, user_context, action_label="editar")

            errors = []

            # Validación de nombre único en update
            if obj_in.name and obj_in.name != campaign.name:
                existing = cls.repository.get_all(
                    session=uow.session,
                    name=obj_in.name,
                    workspace_id=campaign.workspace_id,
                    only_active=False,
                    user_context=user_context
                )
                existing = [e for e in existing if e.id != obj_id]
                if existing:
                    active_ones = [e for e in existing if e.active]
                    if active_ones:
                        errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
                    else:
                        errors.append({"field": "name", "message": f"Ya existe una campaña desactivada llamada '{obj_in.name}' en este espacio de trabajo. Reactívela o use otro nombre."})

            # Validación Crítica: No cambiar lead_flow_id si ya tiene leads
            if obj_in.lead_flow_id and obj_in.lead_flow_id != campaign.lead_flow_id:
                
                leads_count = uow.session.query(Lead).filter_by(campaign_id=obj_id).count()
                
                if leads_count > 0:
                    errors.append({
                        "field": "lead_flow_id", 
                        "message": "No se puede cambiar el flujo de leads porque esta campaña ya tiene prospectos asignados. Cree una nueva campaña."
                    })
                else:
                    # Si no tiene leads, validamos que el nuevo flujo exista en la misma org
                    lead_flow = cls.lead_flow_repository.get_by_id(uow.session, obj_in.lead_flow_id, user_context=user_context)
                    if not lead_flow or lead_flow.organization_id != campaign.organization_id:
                        errors.append({"field": "lead_flow_id", "message": "El flujo de leads especificado no es válido o no pertenece a esta organización."})

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            updated_campaign = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            cls._log_audit(
                session=uow.session,
                obj=updated_campaign,
                action=SystemAuditLogAction.UPDATED,
                changes=obj_in.model_dump(exclude_unset=True),
                user_id=user_context.user.id if user_context and user_context.user else None
            )

            return updated_campaign

        return cls._execute(action="Actualizar Campaña", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False):
        # Hallazgo #19: mismo chequeo que update() — antes el genérico de
        # BaseService solo exigía el permiso RBAC (campaign:delete), sin mirar
        # creador/owner.
        with UnitOfWork() as uow:
            campaign = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not campaign:
                cls._not_found(obj_id)
            cls._assert_can_modify_campaign(campaign, user_context, action_label="eliminar")
        return super().delete(obj_id, user_context=user_context, force=force)

    @classmethod
    def deactivate(cls, obj_id: int, user_context: Optional[UserContext] = None):
        # Hallazgo #19: mismo chequeo que update()/delete().
        with UnitOfWork() as uow:
            campaign = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not campaign:
                cls._not_found(obj_id)
            cls._assert_can_modify_campaign(campaign, user_context, action_label="desactivar")
        return super().deactivate(obj_id, user_context=user_context)
