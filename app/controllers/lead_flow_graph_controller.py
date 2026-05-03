from fastapi import APIRouter, Depends
from app.controllers.base_controller import get_current_user_roles
from app.core.security import UserContext
from app.services.lead_flow_orchestrator_service import LeadFlowOrchestratorService
from app.schemas.lead_flow_schema import LeadFlowGraphPayload

router = APIRouter(prefix="/lead_flows", tags=["Lead Flows Graph"])

@router.post("/graph", response_model=dict) # Cambiar dict por LeadFlowDetailedResponse
def save_lead_flow_graph(
    payload: LeadFlowGraphPayload,
    user_context: UserContext = Depends(get_current_user_roles)
):
    """
    Guarda el lienzo completo de un Flujo de Leads (Flow, States y Transitions).
    Si se envía `id` en el payload, actualiza el flujo existente. Si no, crea uno nuevo.
    Para crear nuevos estados, enviar `id` negativo (ej: -1, -2) y usarlos en las transiciones.
    """
    flow_id = LeadFlowOrchestratorService.save_graph(payload=payload, user_context=user_context)
    return {"message": "Grafo guardado exitosamente", "id": flow_id}