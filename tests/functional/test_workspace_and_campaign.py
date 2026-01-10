def test_workspace_create(client):

    payload = {
        "name": "Workspace Test Create",
        "description": "Descripción del workspace de prueba"
    }

    response = client.post("/workspaces/", json=payload)
    
    # 1. Verificar éxito HTTP
    assert response.status_code == 200, f"Error: {response.text}"
    
    data = response.json()
    assert data["id"] is not None
    
    val_nombre = data["name"]
    assert val_nombre is not None
    assert val_nombre == "Workspace Test Create"


def test_workspace_delete(client):

    payload = {
        "name": "Workspace Test Create",
        "description": "Descripción del workspace de prueba"
    }

    response = client.post("/workspaces/", json=payload)

    response = client.delete(f"/workspaces/{response.json()['id']}/")
    
    assert response.status_code == 200, f"Error: {response.text}"
    assert response.json()["action"] == "deleted"

def test_workspace_update(client):

    payload = {
        "name": "Workspace Test Create",
        "description": "Descripción del workspace de prueba"
    }

    response = client.post("/workspaces/", json=payload)
    
    assert response.status_code == 200, f"Error: {response.text}"
    
    workspace_id = response.json()["id"]

    payload_updated = {
        "name": "Workspace Test Updated",
        "description": "Descripción del workspace de prueba"
    }

    response = client.put(f"/workspaces/{workspace_id}/", json=payload_updated)

    assert response.status_code == 200, f"Error: {response.text}"
    assert response.json()["name"] == "Workspace Test Updated"

def test_workspace_delete_when_exists_campaign(client):

    payload = {
        "name": "Workspace Test Create",
        "description": "Descripción del workspace de prueba"
    }

    response = client.post("/workspaces/", json=payload)

    assert response.status_code == 200, f"Error: {response.text}"
    
    workspace_id = response.json()["id"]

    payload_campaign = {
        "name": "Campaign Test",
        "description": "Descripción de la campaña de prueba",
        "workspace_id": workspace_id
    }

    response = client.post("/campaigns/", json=payload_campaign)

    assert response.status_code == 200, f"Error: {response.text}"

    response = client.delete(f"/workspaces/{workspace_id}/")
    
    assert response.status_code == 200, f"Error: {response.text}"
    assert response.json()["action"] == "disabled"