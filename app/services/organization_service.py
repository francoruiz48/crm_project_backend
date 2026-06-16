from typing import Optional
from app.core.constans import INITIAL_ROUTES_STATES, INITIAL_STATES, SystemAuditLogAction
from app.models.lead_contact_state import LeadContactState
from app.models.lead_field_section import LeadFieldSection
from app.services.base_service import BaseService
from app.db.repository.organization_repository import OrganizationRepository
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.core.security import UserContext
from app.models.security_models import UserOrganization

class OrganizationService(BaseService):
    repository = OrganizationRepository

    @classmethod
    def _create_default_contact_states(cls, session, org_id: int):

        """Crea estados de contacto predeterminados para la organización"""
        default_contact_states = [
            {"name": "No Contactado", "color": "#6B7280", "is_initial": True, "order": 1},   
            {"name": "Esperando Respuesta", "color": "#8B5CF6", "is_initial": False, "order": 2},    
            {"name": "En Conversación", "color": "#3B82F6", "is_initial": False, "order": 3},     
            {"name": "Rechazado", "color": "#BE0D0D", "is_initial": False, "order": 4},
        ]
        
        for state_data in default_contact_states:
            new_state = LeadContactState(
                name=state_data["name"],
                color=state_data["color"],
                is_initial=state_data["is_initial"],
                order=state_data["order"],
                organization_id=org_id
            )
            session.add(new_state)

    @classmethod
    def _create_default_sections(cls, session, org_id: int):

        """Crea secciones de campos predeterminadas para la organización"""
        default_sections = [
            {"name": "Información básica"},
        ]
        
        for section_data in default_sections:
            new_section = LeadFieldSection(
                name=section_data["name"],
                organization_id=org_id
            )
            session.add(new_section)

    @classmethod
    def _create_default_lead_flow(cls, session, org_id: int, user_context: Optional[UserContext] = None):
        """Genera un embudo de ventas genérico para la nueva organización"""
        created_by = user_context.user.id if user_context and user_context.user else None
        # 1. Crear el Flujo Base
        flow = LeadFlow(name="Flujo de Ventas Predeterminado", organization_id=org_id, created_by=created_by)
        session.add(flow)
        session.flush() # Necesario para obtener flow.id

        # 2. Definir los Estados
        states_data = INITIAL_STATES

        created_states = []
        for data in states_data:
            state = LeadState(lead_flow_id=flow.id, organization_id=org_id, created_by=created_by, **data)
            session.add(state)
            created_states.append(state)
        
        session.flush() # Obtenemos los IDs de todos los estados

        # 3. Construir el Grafo (Las Transiciones)
        # Índices: 0(Ing), 1(Cont), 2(Reu), 3(Prop), 4(Venta), 5(NoInt)
        routes = INITIAL_ROUTES_STATES

        for from_idx, to_idx in routes:
            transition = LeadStateTransition(
                lead_flow_id=flow.id,
                from_state_id=created_states[from_idx].id,
                to_state_id=created_states[to_idx].id,
                created_by=created_by
            )
            session.add(transition)

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None, **kwargs):
        def do_create(uow):
            from fastapi import HTTPException, status
            user_id = user_context.user.id if user_context and user_context.user else None
            is_superuser = user_context.is_superuser if user_context else False

            # Validar límite: usuarios comunes solo pueden ser owner de 1 organización
            if user_id and not is_superuser:
                existing_owned = uow.session.query(UserOrganization).filter_by(
                    user_id=user_id,
                    is_owner=True,
                ).first()
                if existing_owned:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Ya sos propietario de una organización. Solo se permite una por usuario.",
                    )

            # 1. Creamos la organización normalmente
            org_data = obj_in.model_dump(exclude_unset=True)
            org_data.update(kwargs)
            org = cls.repository.create(uow.session, org_data, user_context=user_context)
            uow.session.flush() # Obligatorio para tener org.id
            
            # 2. Inyectar el flujo por defecto
            cls._create_default_lead_flow(uow.session, org.id, user_context=user_context)

            cls._create_default_contact_states(uow.session, org.id)

            cls._create_default_sections(uow.session, org.id)
            
            # --- 3. CORONAR AL CREADOR COMO OWNER ---
            if user_id:
                user_org = UserOrganization(
                    user_id=user_id,
                    organization_id=org.id,
                    is_owner=True
                )
                uow.session.add(user_org)
            # ----------------------------------------

            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, org, action=SystemAuditLogAction.CREATED, changes=org_data, user_id=user_id)
            
            return org

        return cls._execute(action="Crear Organización", func=do_create)