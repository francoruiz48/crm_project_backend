from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from app.db.unit_of_work import UnitOfWork
from app.services.base_service import BaseService
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.db.repository.lead_flow_repository import LeadFlowRepository

class LeadFlowOrchestratorService(BaseService):
    repository = LeadFlowRepository()
    
    @classmethod
    def save_graph(cls, payload, user_context: Optional[UserContext] = None):
        def do_save(uow):
            org_id = user_context.organization_id if user_context and user_context.organization_id else TENANT_ORG_ID
            created_by = user_context.user.id if user_context and user_context.user else None
            
            # ==========================================
            # 1. RESOLVER EL PADRE (LEAD FLOW)
            # ==========================================
            flow_id = payload.id
            
            name_query = uow.session.query(LeadFlow).filter(
                LeadFlow.name.ilike(payload.name),
                LeadFlow.organization_id == org_id
            )
            if flow_id:
                name_query = name_query.filter(LeadFlow.id != flow_id)
                
            if name_query.first():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "name", "message": f"Ya existe un flujo llamado '{payload.name}'."}])

            if flow_id:
                flow_obj = uow.session.query(LeadFlow).filter_by(id=flow_id, organization_id=org_id).first()
                if not flow_obj: cls._not_found(flow_id)
                flow_obj.name = payload.name
                flow_obj.description = payload.description
                flow_obj.updated_by = created_by
            else:
                flow_obj = LeadFlow(name=payload.name, description=payload.description, organization_id=org_id, created_by=created_by)
                uow.session.add(flow_obj)
                uow.session.flush() 
                flow_id = flow_obj.id

            # ==========================================
            # 2. CREAR Y ACTUALIZAR ESTADOS (NODOS)
            # ==========================================
            initial_states = [s for s in payload.states if s.is_initial]
            if len(initial_states) != 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "states", "message": "El flujo debe tener exactamente un (1) estado inicial."}])

            existing_states = uow.session.query(LeadState).filter_by(lead_flow_id=flow_id).all()
            existing_states_map = {s.id: s for s in existing_states}
            
            payload_state_ids = [s.id for s in payload.states if s.id and s.id > 0]
            
            id_translation_map = {} 
            open_order_counter = 1
            
            for state_node in payload.states:
                # Defensa: si manda id 0 o negativo, es nuevo
                is_new = state_node.id is None or state_node.id <= 0 
                
                calc_order = None
                if state_node.category == "OPEN":
                    calc_order = open_order_counter
                    open_order_counter += 1

                if is_new:
                    new_state = LeadState(
                        lead_flow_id=flow_id,
                        name=state_node.name,
                        category=state_node.category,
                        is_initial=state_node.is_initial,
                        order=calc_order,
                        color=state_node.color if state_node.color else None,
                        position_x=state_node.position_x,
                        position_y=state_node.position_y,
                        organization_id=org_id,
                        created_by=created_by
                    )
                    uow.session.add(new_state)
                    uow.session.flush() # Obtenemos el ID real para las transiciones
                    id_translation_map[state_node.id] = new_state.id
                else:
                    db_state = existing_states_map.get(state_node.id)
                    if db_state:
                        db_state.name = state_node.name
                        db_state.category = state_node.category
                        db_state.is_initial = state_node.is_initial
                        db_state.order = calc_order
                        db_state.color = state_node.color if state_node.color else None
                        db_state.position_x = state_node.position_x
                        db_state.position_y = state_node.position_y
                        db_state.updated_by = created_by
                        id_translation_map[state_node.id] = db_state.id
                        

            # ==========================================
            # 3. TRADUCCIÓN Y MAPEO DE TRANSICIONES
            # ==========================================
            existing_transitions = uow.session.query(LeadStateTransition).filter_by(lead_flow_id=flow_id).all()
            existing_t_map = {(t.from_state_id, t.to_state_id): t for t in existing_transitions}
            
            incoming_pairs = set()
            for edge in payload.transitions:
                real_from = id_translation_map.get(edge.from_state_id)
                real_to = id_translation_map.get(edge.to_state_id)
                
                if not real_from or not real_to:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "transitions", "message": "Transición apunta a un estado inválido o no guardado."}])
                
                incoming_pairs.add((real_from, real_to))

            # ==========================================
            # 4. ELIMINACIÓN SEGURA (ORDEN ESTRICTO)
            # ==========================================
            # A. Borramos Transiciones PRIMERO
            for pair, db_trans in existing_t_map.items():
                if pair not in incoming_pairs:
                    uow.session.delete(db_trans)

            uow.session.flush() # ⚡ CRÍTICO: Fuerza a PostgreSQL a borrar las dependencias ya mismo.

            # B. Ahora sí, borramos los Estados obsoletos con seguridad
            for db_state in existing_states:
                if db_state.id not in payload_state_ids:
                    uow.session.delete(db_state)

            uow.session.flush() # ⚡ CRÍTICO: Fuerza a borrar los nodos limpios.

            # ==========================================
            # 5. CREACIÓN DE NUEVAS TRANSICIONES
            # ==========================================
            for pair in incoming_pairs:
                if pair not in existing_t_map:
                    new_trans = LeadStateTransition(
                        lead_flow_id=flow_id,
                        from_state_id=pair[0],
                        to_state_id=pair[1],
                        created_by=created_by
                    )
                    uow.session.add(new_trans)
            
            uow.session.flush()

            # ==========================================
            # 6. VALIDACIÓN DE REGLAS FINALES (Callejones sin salida)
            # ==========================================
            final_states = uow.session.query(LeadState).filter_by(lead_flow_id=flow_id).all()
            for state in final_states:
                if state.category == "OPEN":
                    exits = sum(1 for pair in incoming_pairs if pair[0] == state.id)
                    if exits == 0:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "transitions", "message": f"Diseño inválido: El estado '{state.name}' es un callejón sin salida (no tiene rutas hacia adelante)."}])

            # Auditoría y Retorno
            cls._log_audit(uow.session, flow_obj, action="GRAPH_SAVED", changes=None, user_id=created_by)
            
            return flow_obj.id

        return cls._execute(action="Guardar Grafo de Lead Flow", func=do_save)