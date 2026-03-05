from fastapi import status, HTTPException
from sqlalchemy import desc
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.core.exceptions.exceptions import ValidationError
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.models.campaign import Campaign
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository

    @classmethod
    def _clone_lead_flow(cls, session, new_campaign, created_by):
        """
        Busca una campaña origen válida y clona sus estados y transiciones.
        Prioridad 1: Última campaña del MISMO workspace que tenga estados.
        Prioridad 2: Última campaña de la MISMA organización que tenga estados.
        """
        source_campaign_id = None

        # 1A. Buscar en el mismo Workspace
        source_camp_local = session.query(Campaign.id).join(
            LeadState, LeadState.campaign_id == Campaign.id
        ).filter(
            Campaign.workspace_id == new_campaign.workspace_id,
            Campaign.id != new_campaign.id  # Excluir la actual por las dudas
        ).order_by(desc(Campaign.created_at)).first()

        if source_camp_local:
            source_campaign_id = source_camp_local.id
        else:
            # 1B. Fallback: Buscar en toda la Organización (Cualquier otro workspace)
            source_camp_global = session.query(Campaign.id).join(
                LeadState, LeadState.campaign_id == Campaign.id
            ).filter(
                Campaign.organization_id == new_campaign.organization_id,
                Campaign.id != new_campaign.id
            ).order_by(desc(Campaign.created_at)).first()
            
            if source_camp_global:
                source_campaign_id = source_camp_global.id

        # 2. Si encontramos un flujo para copiar, procedemos
        if source_campaign_id:
            # Traemos los estados viejos
            old_states = session.query(LeadState).filter_by(campaign_id=source_campaign_id).all()
            
            # Diccionario para saber qué ID viejo corresponde a qué ID nuevo
            id_mapping = {}

            for old_state in old_states:
                new_state = LeadState(
                    campaign_id=new_campaign.id,
                    organization_id=new_campaign.organization_id,
                    name=old_state.name,
                    color=old_state.color,
                    category=old_state.category,
                    is_initial=old_state.is_initial,
                    order=old_state.order,
                    active=old_state.active,
                    created_by=created_by
                )
                session.add(new_state)
                session.flush() # Forzamos el insert para obtener el new_state.id
                
                id_mapping[old_state.id] = new_state.id

            # 3. Traemos las transiciones (el grafo) y las recreamos con los IDs nuevos
            old_transitions = session.query(LeadStateTransition).filter_by(campaign_id=source_campaign_id).all()
            
            for ot in old_transitions:
                # Verificamos que ambos nodos existan en nuestro mapeo (por integridad)
                if ot.from_state_id in id_mapping and ot.to_state_id in id_mapping:
                    new_transition = LeadStateTransition(
                        campaign_id=new_campaign.id,
                        from_state_id=id_mapping[ot.from_state_id],
                        to_state_id=id_mapping[ot.to_state_id],
                        active=ot.active,
                        created_by=created_by
                    )
                    session.add(new_transition)
                    
            # El session.commit() global del UnitOfWork se encargará de guardar todo esto.

    @classmethod
    def create(cls, obj_in, created_by=None):
        
        def do_create(uow):
            errors = []

            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id)
            if not workspace:
                errors.append({"field": "workspace_id", "message": "El espacio de trabajo especificado no existe."})
            else:
                existing = cls.repository.get_all(
                    session=uow.session, 
                    name=obj_in.name, 
                    workspace_id=obj_in.workspace_id,
                    only_active=True
                )
                
                if existing:
                    errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
            

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump()

            # 1. Crear la campaña base
            new_campaign = cls.repository.create(uow.session, data, created_by)

            # 2. Inyectar el clonador del flujo de estados
            cls._clone_lead_flow(uow.session, new_campaign, created_by)

            return new_campaign

        return cls._execute(action="Crear Campaña", func=do_create)