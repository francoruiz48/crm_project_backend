from tests.fixtures.db_fixtures import db_engine, db_session
from tests.fixtures.client import client
from tests.fixtures.data_seeds import initial_structure, initial_fields

import pytest
from tests.helpers.api_helpers import ApiClient

@pytest.fixture
def api(client, initial_structure):
    """Fixture que devuelve el helper de API ya configurado con el cliente y la organización del test"""
    # Tomamos el ID puro que generó el fixture initial_structure
    org_id = initial_structure["org_id"]
    
    # Inicializamos el cliente inyectando ese ID específico
    return ApiClient(client, org_id=org_id)