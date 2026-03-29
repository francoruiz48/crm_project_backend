from typing import Dict, Any, Optional, Union, List
from app.core.context import TENANT_ORG_ID

def validate(response, expected_status: Union[int, List[int], None] = None, msg: str = ""):
    if expected_status is None:
        target_statuses = [200, 201]
    elif expected_status is False:
        return response 
    elif isinstance(expected_status, int):
        target_statuses = [expected_status]
    else:
        target_statuses = expected_status

    assert response.status_code in target_statuses, \
        f"Fallo {msg}: Esperaba {target_statuses}, recibió {response.status_code}. Body: {response.text}"

    try:
        return response.json()
    except Exception:
        return response

class ApiClient:
    def __init__(self, client, org_id: int = 1):
        self.client = client
        self.org_id = org_id

    @property
    def headers(self):
        """
        Cada vez que el test usa 'api.headers', esta función se ejecuta,
        inyecta el Tenant en la memoria y devuelve el diccionario.
        """
        return self._inject_context()

    def _inject_context(self, custom_org_id=None):
        org_id_to_use = custom_org_id if custom_org_id else self.org_id
        TENANT_ORG_ID.set(org_id_to_use)
        return {"X-Organization-Id": str(org_id_to_use)}
    


    # ==========================
    # ORGANIZACIÓN Y WORKSPACE
    # ==========================
    def create_organization(self, name="Org Test", expected_status=None) -> Dict:
        headers = self._inject_context()
        resp = self.client.post("/organizations/", json={"name": name}, headers=headers)
        return validate(resp, expected_status, "crear Organization")

    def create_workspace(self, name="Workspace Test", expected_status=None, is_public: bool = True, custom_org_id=None) -> Dict:
        headers = self._inject_context(custom_org_id)
        payload = {"name": name, "is_public": is_public}
        resp = self.client.post("/workspaces/", json=payload, headers=headers)
        return validate(resp, expected_status, "crear Workspace")

    # ==========================
    # CAMPAÑAS
    # ==========================
    def create_campaign(self, workspace_id: int, name="Campaña Test", lead_flow_id: int = 1, is_public: bool = True, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "name": name, 
            "workspace_id": workspace_id, 
            "lead_flow_id": lead_flow_id,
            "is_public": is_public,
            "description": "Created by ApiHelper",
            "active": True
        }
        resp = self.client.post("/campaigns/", json=payload, headers=headers)
        return validate(resp, expected_status, "crear Campaign")

    # ==========================
    # EQUIPOS Y ACCESOS
    # ==========================
    def create_team(self, name: str, is_visibility_shared: bool = True, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {"name": name, "is_visibility_shared": is_visibility_shared}
        resp = self.client.post("/teams/", json=payload, headers=headers)
        return validate(resp, expected_status, f"crear Team '{name}'")

    def add_team_member(self, team_id: int, user_id: int, role: str = "AGENT", expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {"team_id": team_id, "user_id": user_id, "role": role}
        resp = self.client.post("/team_members/", json=payload, headers=headers)
        return validate(resp, expected_status, f"agregar User {user_id} a Team {team_id}")

    def grant_workspace_access(self, team_id: int, workspace_id: int, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {"team_id": team_id, "workspace_id": workspace_id}
        resp = self.client.post("/team_workspace_access/", json=payload, headers=headers)
        return validate(resp, expected_status, "acceso Workspace")

    def grant_campaign_access(self, team_id: int, campaign_id: int, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {"team_id": team_id, "campaign_id": campaign_id}
        resp = self.client.post("/team_campaign_access/", json=payload, headers=headers)
        return validate(resp, expected_status, "acceso Campaign")
    
    # ==========================
    # ENRUTAMIENTO Y ASIGNACIÓN
    # ==========================
    def create_routing_rule(self, condition_type: str, condition_target_id: int, condition_value: str, 
                            target_team_id: int, campaign_id: int = None, order: int = None, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "condition_type": condition_type,
            "condition_target_id": condition_target_id,
            "condition_value": condition_value,
            "target_team_id": target_team_id
        }
        if campaign_id: payload["campaign_id"] = campaign_id
        if order: payload["order"] = order
        
        resp = self.client.post("/lead_routing_rules/", json=payload, headers=headers)
        return validate(resp, expected_status, "crear Regla de Enrutamiento")

    def bulk_assign(self, lead_ids: list, target_team_id: int = None, target_user_id: int = None, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {"lead_ids": lead_ids}
        if target_team_id: payload["target_team_id"] = target_team_id
        if target_user_id: payload["target_user_id"] = target_user_id
        
        # OJO: Asumiendo que configuraste el PATCH en el LeadController como hablamos
        resp = self.client.patch("/leads/bulk-assign", json=payload, headers=headers)
        return validate(resp, expected_status, "asignación masiva")

    # ==========================
    # CAMPOS Y SECCIONES
    # ==========================
    def ensure_section(self, name="General") -> int:
        headers = self._inject_context()
        payload = {"name": name}
        resp = self.client.post("/lead_field_sections/", json=payload, headers=headers)
        if resp.status_code in [200, 201]:
            return resp.json()['id']
        return 1

    def create_lead_field(self, campaign_id: int, name: str, field_type_code: str, 
                      subtype_code: str = None, required: bool = False, is_primary: bool = False,
                      section_id: int = 1, calculation_expression=None, expected_status=None, **kwargs) -> Dict:
        
        headers = self._inject_context()
        payload = {
            "campaign_id": campaign_id,
            "name": name,
            "field_type_code": field_type_code,
            "required": required,
            "lead_field_section_id": section_id,
            "is_visible": True,
            "is_primary": is_primary
        }
        if subtype_code:
            payload["field_subtype_code"] = subtype_code
        if calculation_expression:
            payload["calculation_expression"] = calculation_expression

        payload.update(kwargs)
            
        resp = self.client.post("/lead_fields/", json=payload, headers=headers)
        return validate(resp, expected_status, f"crear Campo '{name}'")

    def create_lead_field_from_template(self, campaign_id: int, template_code: str, 
                                   required: bool = False, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "campaign_id": campaign_id,
            "field_template_code": template_code,
            "required": required,
            "lead_field_section_id": 1,
            "is_visible": True
        }
        resp = self.client.post("/lead_fields/", json=payload, headers=headers)
        return validate(resp, expected_status, f"crear Campo Template '{template_code}'")
    
    def reorder_lead_fields(self, campaign_id: int, orders: list, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "campaign_id": campaign_id,
            "orders": orders # Lista de {"field_id": int, "order": int}
        }
        resp = self.client.patch("/lead_fields/reorder/bulk", json=payload, headers=headers)
        return validate(resp, expected_status, "reordenar campos")

    # ==========================
    # LEADS
    # ==========================
    def create_lead(self, campaign_id: int, values: list, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "campaign_id": campaign_id,
            "values": values
        }
        resp = self.client.post("/leads/", json=payload, headers=headers)
        return validate(resp, expected_status, "crear Lead")

    def update_lead(self, lead_id: int, values: list, campaign_id: int, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "campaign_id": campaign_id,
            "values": values
        }
        resp = self.client.put(f"/leads/{lead_id}", json=payload, headers=headers)
        return validate(resp, expected_status, f"actualizar Lead {lead_id}")

    def get_lead(self, lead_id: int, expected_status=None) -> Dict:
        headers = self._inject_context()
        resp = self.client.get(f"/leads/{lead_id}", headers=headers)
        return validate(resp, expected_status, f"obtener Lead {lead_id}")

    def delete_lead(self, lead_id: int, expected_status=None) -> Dict:
        headers = self._inject_context()
        resp = self.client.delete(f"/leads/{lead_id}", headers=headers)
        return validate(resp, expected_status, f"borrar Lead {lead_id}")

    # ==========================
    # VALIDACIONES Y REGLAS
    # ==========================
    def create_rule(self, field_id: int, name: str, expression: str, 
                    error_msg: str, expected_status=None) -> Dict:
        headers = self._inject_context()
        payload = {
            "field_id": field_id,
            "name": name,
            "expression": expression,
            "error_message": error_msg,
            "active": True
        }
        resp = self.client.post("/validation_rules/", json=payload, headers=headers)
        return validate(resp, expected_status, "crear Regla Validación")