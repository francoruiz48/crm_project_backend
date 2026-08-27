import pytest

# Definimos los endpoints base y un ID de referencia (del fixture) para probar el GET ONE
# Estructura: (Endpoint URL, ID para Get One, Query Params extra si hacen falta)
def get_entities_config(structure):
    return [
        ("/organizations/", structure["org_id"], ""),
        ("/workspaces/", structure["workspace_id"], ""),
        ("/campaigns/", structure["campaign_id"], ""),
        ("/nomenclators/", 1, ""), # Asumiendo ID 1 existe por seeds
        ("/validation_rules/", 1, ""), # Asumiendo ID 1 existe
        # Lead Fields y Leads requieren campaign_id obligatorio a veces
        ("/lead_fields/", 1, f"&campaign_id={structure['campaign_id']}"), 
        ("/leads/", 1, f"&campaign_id={structure['campaign_id']}") 
    ]

def test_list_entities_response_schemas(api, initial_structure):
    """
    Prueba GET List con only_active=False y only_active=True
    para verificar que ambos esquemas (Response y DetailResponse) funcionen.
    """
    entities = get_entities_config(initial_structure)

    for base_url, _, extra_query in entities:
        # Caso 1: only_active=False (Suele devolver Response simple)
        url_all = f"{base_url}?only_active=False{extra_query}"
        resp_all = api.client.get(url_all, headers=api.headers)
        assert resp_all.status_code == 200, f"Fallo List All en {base_url}: {resp_all.text}"
        
        # Caso 2: only_active=True (Suele devolver DetailResponse enriquecido)
        url_active = f"{base_url}?only_active=True{extra_query}"
        resp_active = api.client.get(url_active, headers=api.headers)
        assert resp_active.status_code == 200, f"Fallo List Active en {base_url}: {resp_active.text}"

        # Validación básica de estructura (Paginación o Lista)
        data = resp_active.json()
        assert "items" in data or isinstance(data, list), f"Formato inválido en {base_url}"