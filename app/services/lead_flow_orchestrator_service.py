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
from app.models.lead import Lead
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.core.constans import SystemAuditLogAction

class LeadFlowOrchestratorService(BaseService):
    repository = LeadFlowRepository()
    
    @classmethod
    def save_graph(cls, payload, user_context: Optional[UserContext] = None):
        def do_save(uow):
            org_id = user_context.organization_id if user_context and user_context.organization_id else TENANT_ORG_ID.get()
            created_by = user_context.user.id if user_context and user_context.user else None
            
            # ==========================================
            # 1. RESOLVER EL PADRE (LEAD FLOW)
            # ==========================================
            # payload.id llega como public_uuid (Fase 3, ver backend/AGENTS.md §18); se resuelve
            # una vez al id interno acá y de ahí en más flow_id es siempre el int interno, igual
            # que antes de la migración.
            flow_id = None
            if payload.id:
                flow_id = LeadFlowRepository.get_internal_id_by_public_uuid(uow.session, payload.id)
                if flow_id is None:
                    cls._not_found(payload.id)

            name_query = uow.session.query(LeadFlow).filter(
                LeadFlow.name.ilike(payload.name),
                LeadFlow.organization_id == org_id,
                LeadFlow.active.is_(True)
            )
            if flow_id:
                name_query = name_query.filter(LeadFlow.id != flow_id)
                
            if name_query.first():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "name", "message": f"Ya existe un flujo llamado '{payload.name}'."}])

            if flow_id:
                flow_obj = uow.session.query(LeadFlow).filter_by(id=flow_id, organization_id=org_id, active=True).first()
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

            # Validación: el estado inicial debe ser de categoría OPEN
            if initial_states[0].category != "OPEN":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "states", "message": "El estado inicial debe ser de categoría OPEN."}])

            existing_states = uow.session.query(LeadState).filter_by(lead_flow_id=flow_id, active=True).all()
            existing_states_map = {s.id: s for s in existing_states}

            # Un estado existente llega identificado por su public_uuid (string); uno nuevo, por
            # un int negativo/None (placeholder temporal, ver StateNodeSchema.id). Se resuelven en
            # bloque los uuids a id interno antes del loop (Fase 3, ver backend/AGENTS.md §18).
            existing_state_uuids = [s.id for s in payload.states if isinstance(s.id, str)]
            uuid_to_internal_state_id = LeadStateRepository.get_internal_ids_by_public_uuids(uow.session, existing_state_uuids)

            payload_state_ids = []
            id_translation_map = {}
            open_order_counter = 1

            for state_node in payload.states:
                is_new = not isinstance(state_node.id, str)

                calc_order = None
                if state_node.category == "OPEN":
                    # Respetar el order del payload si viene provisto; si no, usar el counter secuencial
                    if state_node.order is not None and state_node.order > 0:
                        calc_order = state_node.order
                    else:
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
                    payload_state_ids.append(new_state.id)
                else:
                    real_existing_id = uuid_to_internal_state_id.get(state_node.id)
                    if real_existing_id is None:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "states", "message": f"Estado '{state_node.name}' no encontrado."}])
                    db_state = existing_states_map.get(real_existing_id)
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
                        payload_state_ids.append(db_state.id)


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
            # 3.5 VALIDACIÓN DE REGLAS (pre-mutación)
            # ==========================================
            # Callejones sin salida: validar ANTES de tocar la DB para dar error limpio
            for state_node in payload.states:
                if state_node.category == "OPEN":
                    real_id = id_translation_map.get(state_node.id)
                    exits = sum(1 for pair in incoming_pairs if pair[0] == real_id)
                    if exits == 0:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "transitions", "message": f"Diseño inválido: El estado '{state_node.name}' es un callejón sin salida (no tiene rutas hacia adelante)."}])

            # ==========================================
            # 4. ELIMINACIÓN SEGURA (ORDEN ESTRICTO)
            # ==========================================
            # A. Borramos Transiciones PRIMERO
            for pair, db_trans in existing_t_map.items():
                if pair not in incoming_pairs:
                    uow.session.delete(db_trans)

            uow.session.flush()  # ⚡ CRÍTICO: Fuerza a PostgreSQL a borrar las dependencias ya mismo.

            # B. Soft-delete de los Estados obsoletos (con verificación de leads activos)
            for db_state in existing_states:
                if db_state.id not in payload_state_ids:
                    leads_en_estado = uow.session.query(Lead).filter_by(
                        current_state_id=db_state.id,
                        active=True
                    ).count()
                    if leads_en_estado > 0:
                        raise HTTPException(
                            status.HTTP_400_BAD_REQUEST,
                            detail=[{"field": "states", "message": f"No se puede eliminar el estado '{db_state.name}': hay {leads_en_estado} lead(s) activo(s) en ese estado."}]
                        )
                    # Soft delete para preservar integridad del historial
                    db_state.active = False
                    db_state.updated_by = created_by

            uow.session.flush()  # ⚡ CRÍTICO: Fuerza a marcar los nodos eliminados.

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

            # Auditoría y Retorno
            cls._log_audit(uow.session, flow_obj, action=SystemAuditLogAction.UPDATED, changes=None, user_id=created_by)

            # public_uuid, no el id interno -- así el frontend puede usarlo directo en la URL
            # /lead-flow-editor/{id} y en llamadas posteriores (GET/PUT genéricos), igual que
            # cualquier otra entidad desde Fase 3 (ver backend/AGENTS.md §18).
            return flow_obj.public_uuid

        return cls._execute(action="Guardar Grafo de Lead Flow", func=do_save)