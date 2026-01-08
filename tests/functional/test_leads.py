def test_get_empty_leads(client):
    """GET /leads/ cuando no hay leads"""
    response = client.get("/leads/")
    assert response.status_code == 200
    #assert response.json() == []

def test_create_lead_success(client, initial_fields):
    """POST /leads/ exitoso"""
    payload = {
        "values": [
            {"field_id": initial_fields["nombre"].id, "value": "Franco"},
            {"field_id": initial_fields["apellido"].id, "value": "Ruiz"}
        ]
    }
    response = client.post("/leads/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "fields" in data
    assert len(data["fields"]) == 2
    assert data["fields"][0]["name"] == "Nombre"
    assert data["fields"][0]["value"] == "Franco"
    assert data["fields"][0]["required"] is True

def test_get_leads(client, initial_fields):
    """GET /leads/ después de crear un lead"""
    payload = {
        "values": [
            {"field_id": initial_fields["nombre"].id, "value": "Franco"},
            {"field_id": initial_fields["apellido"].id, "value": "Ruiz"}
        ]
    }
    client.post("/leads/", json=payload)
    response = client.get("/leads/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    lead = data[0]
    assert "fields" in lead
    fields = {f["name"]: f for f in lead["fields"]}
    assert fields["Nombre"]["value"] == "Franco"
    assert fields["Apellido"]["value"] == "Ruiz"

def test_create_lead_missing_values(client):
    """POST /leads/ con payload vacío"""
    payload = {}
    response = client.post("/leads/", json=payload)
    assert response.status_code == 422  # Validation error de Pydantic
