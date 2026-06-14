"""
conftest.py actualizado
========================
Agrega los fixtures multi-usuario como OPT-IN sin tocar los existentes.
Los tests actuales siguen funcionando sin cambios.
"""
from tests.fixtures.db_fixtures import db_engine, db_session
from tests.fixtures.client import client
from tests.fixtures.data_seeds import initial_structure, initial_fields
# Importar los nuevos fixtures multi-usuario (OPT-IN)
from tests.fixtures.user_fixtures import team_users, api_multi
# Fixtures de aislamiento multi-tenant
from tests.fixtures.org_fixtures import ctx_alpha, ctx_beta, member_multi

import pytest
from tests.helpers.api_helpers import ApiClient


@pytest.fixture
def api(client, initial_structure):
    """
    Fixture original sin cambios.
    Usa el superadmin hardcodeado en security.py.
    Todos los tests existentes siguen funcionando igual.
    """
    org_id = initial_structure["org_id"]
    return ApiClient(client, org_id=org_id)
