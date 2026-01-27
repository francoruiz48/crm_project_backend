from typing import Dict, Any, Optional, Union, List

def validate(response, expected_status: Union[int, List[int], None] = None, msg: str = ""):
    """
    Valida el status code de la respuesta.
    - Si expected_status es None (o no se pasa), por defecto valida éxito (200, 201).
    - Si expected_status es explícito (ej: 400), valida ese código.
    - Si expected_status es False, NO valida nada y devuelve la respuesta cruda (requests.Response).
    """
    # 1. Configurar valores por defecto (Happy Path)
    if expected_status is None:
        target_statuses = [200, 201]
    elif expected_status is False:
        return response # Retornamos raw response sin validar
    elif isinstance(expected_status, int):
        target_statuses = [expected_status]
    else:
        target_statuses = expected_status

    # 2. Assert
    assert response.status_code in target_statuses, \
        f"Fallo {msg}: Esperaba {target_statuses}, recibió {response.status_code}. Body: {response.text}"

    # 3. Retorno inteligente (JSON si se puede, sino Response)
    try:
        return response.json()
    except Exception:
        return response

class ApiClient:
    def __init__(self, client):
        self.client = client

    # ==========================
    # ORGANIZACIÓN Y WORKSPACE
    # ==========================
    def create_organization(self, name="Org Test", expected_status=None) -> Dict:
        resp = self.client.post("/organizations/", json={"name": name})
        return validate(resp, expected_status, "crear Organization")

    def create_workspace(self, org_id: int, name="Workspace Test", expected_status=None) -> Dict:
        payload = {"name": name, "organization_id": org_id}
        resp = self.client.post("/workspaces/", json=payload)
        return validate(resp, expected_status, "crear Workspace")

    # ==========================
    # CAMPAÑAS
    # ==========================
    def create_campaign(self, workspace_id: int, name="Campaña Test", expected_status=None) -> Dict:
        payload = {
            "name": name, 
            "workspace_id": workspace_id, 
            "description": "Created by ApiHelper",
            "active": True
        }
        resp = self.client.post("/campaigns/", json=payload)
        return validate(resp, expected_status, "crear Campaign")

    # ==========================
    # CAMPOS Y SECCIONES
    # ==========================
    def ensure_section(self, name="General") -> int:
        # Este es un helper utilitario, lo dejamos simple o le agregamos manejo manual
        payload = {"name": name}
        resp = self.client.post("/lead_field_sections/", json=payload)
        if resp.status_code in [200, 201]:
            return resp.json()['id']
        # Fallback
        return 1

    def create_lead_field(self, campaign_id: int, name: str, field_type_code: str, 
                     subtype_code: str = None, required: bool = False, is_primary: bool = False,
                     section_id: int = 1, calculation_expression=None, expected_status=None, **kwargs) -> Dict:
        
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
            
        resp = self.client.post("/lead_fields/", json=payload)
        return validate(resp, expected_status, f"crear Campo '{name}'")

    def create_lead_field_from_template(self, campaign_id: int, template_code: str, 
                                   required: bool = False, expected_status=None) -> Dict:
        payload = {
            "campaign_id": campaign_id,
            "field_template_code": template_code,
            "required": required,
            "lead_field_section_id": 1,
            "is_visible": True
        }
        resp = self.client.post("/lead_fields/", json=payload)
        return validate(resp, expected_status, f"crear Campo Template '{template_code}'")

    # ==========================
    # LEADS
    # ==========================
    def create_lead(self, campaign_id: int, values: list, expected_status=None) -> Dict:
        """
        values: [{"field_id": 1, "value": "Juan"}]
        """
        payload = {
            "campaign_id": campaign_id,
            "values": values
        }
        resp = self.client.post("/leads/", json=payload)
        return validate(resp, expected_status, "crear Lead")

    def update_lead(self, lead_id: int, values: list, campaign_id: int, expected_status=None) -> Dict:
        payload = {
            "campaign_id": campaign_id,
            "values": values
        }
        resp = self.client.put(f"/leads/{lead_id}", json=payload)
        return validate(resp, expected_status, f"actualizar Lead {lead_id}")

    def get_lead(self, lead_id: int, expected_status=None) -> Dict:
        resp = self.client.get(f"/leads/{lead_id}")
        return validate(resp, expected_status, f"obtener Lead {lead_id}")

    def delete_lead(self, lead_id: int, expected_status=None) -> Dict:
        resp = self.client.delete(f"/leads/{lead_id}")
        return validate(resp, expected_status, f"borrar Lead {lead_id}")

    # ==========================
    # VALIDACIONES Y REGLAS
    # ==========================
    def create_rule(self, field_id: int, name: str, expression: str, 
                    error_msg: str, org_id: int, expected_status=None) -> Dict:
        payload = {
            "field_id": field_id,
            "organization_id": org_id,
            "name": name,
            "expression": expression,
            "error_message": error_msg,
            "active": True
        }
        resp = self.client.post("/validation_rules/", json=payload)
        return validate(resp, expected_status, "crear Regla Validación")