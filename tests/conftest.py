from tests.fixtures.db_fixtures import db_engine, db_session
from tests.fixtures.client import client
from tests.fixtures.data_seeds import initial_structure, initial_fields

import pytest
from tests.helpers.api_helpers import ApiClient

@pytest.fixture
def api(client):
    """Fixture que devuelve el helper de API ya configurado con el cliente"""
    return ApiClient(client)