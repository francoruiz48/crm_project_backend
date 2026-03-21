from app.core.constans import INITIAL_ROUTES_STATES, INITIAL_STATES
from app.services.base_service import BaseService
from app.db.repository.organization_repository import OrganizationRepository
from app.db.unit_of_work import UnitOfWork

# Importamos los modelos del flujo
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition

class OrganizationService(BaseService):
    repository = OrganizationRepository

    @classmethod
    def _create_default_lead_flow(cls, session, org_id: int, created_by: int):
        """Genera un embudo de ventas genérico para la nueva organización"""
        
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
    def create(cls, obj_in, created_by=None, **kwargs):
        def do_create(uow):
            # Creamos la organización normalmente
            org_data = obj_in.model_dump(exclude_unset=True)
            org_data.update(kwargs)
            org = cls.repository.create(uow.session, org_data, created_by)
            uow.session.flush() # Obligatorio para tener org.id
            
            # --- Inyectar el flujo por defecto ---
            cls._create_default_lead_flow(uow.session, org.id, created_by)
            
            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, org, action="CREATE", changes=org_data, user_id=created_by)
            
            return org

        return cls._execute(action="Crear Organización", func=do_create)