def test_workspace_create(api, initial_structure):
    # Ya no enviamos el organization_id, el sistema lo toma del Header automáticamente
    payload = {
        "name": "Workspace Test Create",
        "description": "Descripción del workspace de prueba"
    }

    response = api.client.post("/workspaces/", json=payload, headers=api.headers)
    
    # 1. Verificar éxito HTTP
    assert response.status_code == 200, f"Error: {response.text}"
    
    data = response.json()
    assert data["id"] is not None
    
    val_nombre = data["name"]
    assert val_nombre is not None
    assert val_nombre == "Workspace Test Create"


def test_workspace_delete(api, initial_structure):
    payload = {
        "name": "Workspace Test Delete",
        "description": "Descripción del workspace de prueba"
    }

    res_create = api.client.post("/workspaces/", json=payload, headers=api.headers)
    ws_id = res_create.json()['id']

    res_delete = api.client.delete(f"/workspaces/{ws_id}/", headers=api.headers)
    
    assert res_delete.status_code == 200, f"Error: {res_delete.text}"
    assert res_delete.json()["action"] == "deleted"


def test_workspace_update(api, initial_structure):
    payload = {
        "name": "Workspace Test Update",
        "description": "Descripción del workspace de prueba"
    }

    res_create = api.client.post("/workspaces/", json=payload, headers=api.headers)
    assert res_create.status_code == 200, f"Error: {res_create.text}"
    
    workspace_id = res_create.json()["id"]

    payload_updated = {
        "name": "Workspace Test Updated",
        "description": "Descripción del workspace de prueba actualizada"
    }

    res_update = api.client.put(f"/workspaces/{workspace_id}/", json=payload_updated, headers=api.headers)

    assert res_update.status_code == 200, f"Error: {res_update.text}"
    assert res_update.json()["name"] == "Workspace Test Updated"


def test_workspace_delete_when_exists_campaign(api, initial_structure):
    # 1. Crear el Workspace
    payload = {
        "name": "Workspace Parent",
        "description": "Workspace que tendrá campañas"
    }

    res_create = api.client.post("/workspaces/", json=payload, headers=api.headers)
    assert res_create.status_code == 200, f"Error: {res_create.text}"
    
    workspace_id = res_create.json()["id"]

    # 2. Crear una Campaña asociada (usando nuestro api_helper para simplificar)
    api.create_campaign(
        workspace_id=workspace_id, 
        name="Campaign Test Bloqueadora", 
        lead_flow_id=initial_structure["lead_flow_id"],
        expected_status=200
    )

    # 3. Intentar Borrar el Workspace (Debería hacer soft-delete / disable en lugar de delete físico)
    res_delete = api.client.delete(f"/workspaces/{workspace_id}/", headers=api.headers)
    
    assert res_delete.status_code == 200, f"Error: {res_delete.text}"
    assert res_delete.json()["action"] == "disabled"