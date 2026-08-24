"""
test_metadata.py
=================
Tests de GET /metadata/dictionaries (ver backend/docs/metadata.md):

  1. Devuelve el diccionario completo, incluida la clave dinámica
     `entity_delete_strategies` (agregada 2026-08-10).
  2. Filtro por `?keys=`.
  3. Claves inexistentes en `?keys=` se ignoran en silencio (no dan error).
  4. No requiere header `X-Organization-Id` (a diferencia de los endpoints
     protegidos con `PermissionChecker`).
  5. `entity_delete_strategies`: forma de la respuesta (claves = nombre de clase
     del modelo, no el código de `SYSTEM_ENTITIES_REGISTRY`) y spot-check de
     valores conocidos, para detectar si algún repo cambia su `delete_strategy`
     sin que nadie lo note.
"""
import pytest
from app.core.constans import DeleteStrategy


class TestMetadataDictionariesEndpoint:
    def test_get_all_dictionaries_returns_expected_keys(self, client, initial_structure):
        org_id = initial_structure["org_id"]
        resp = client.get("/metadata/dictionaries", headers={"X-Organization-Id": str(org_id)})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        expected_keys = {
            "lead_search_operators",
            "routing_condition_types",
            "team_roles",
            "lead_states_categories",
            "lead_view_visibilities",
            "automation_compatibility_matrix",
            "entities",
            "system_audit_log_actions",
            "entity_delete_strategies",
        }
        assert expected_keys.issubset(data.keys())

    def test_get_dictionaries_filtered_by_keys(self, client, initial_structure):
        org_id = initial_structure["org_id"]
        resp = client.get(
            "/metadata/dictionaries",
            params={"keys": "team_roles,entity_delete_strategies"},
            headers={"X-Organization-Id": str(org_id)},
        )
        assert resp.status_code == 200, resp.text
        assert set(resp.json().keys()) == {"team_roles", "entity_delete_strategies"}

    def test_get_dictionaries_ignores_unknown_keys(self, client, initial_structure):
        org_id = initial_structure["org_id"]
        resp = client.get(
            "/metadata/dictionaries",
            params={"keys": "team_roles,esto_no_existe"},
            headers={"X-Organization-Id": str(org_id)},
        )
        assert resp.status_code == 200, resp.text
        # La clave inexistente se ignora en silencio, no rompe ni la devuelve vacía
        assert set(resp.json().keys()) == {"team_roles"}

    def test_get_dictionaries_works_without_org_header(self, client):
        """
        Es contenido estático de solo lectura sin permiso propio (solo requiere sesión
        válida vía get_current_user_roles), a diferencia de los endpoints CRUD genéricos
        que dependen de PermissionChecker y sí exigen X-Organization-Id.
        """
        resp = client.get("/metadata/dictionaries")
        assert resp.status_code == 200, resp.text

    def test_team_roles_dictionary_content(self, client, initial_structure):
        org_id = initial_structure["org_id"]
        resp = client.get(
            "/metadata/dictionaries",
            params={"keys": "team_roles"},
            headers={"X-Organization-Id": str(org_id)},
        )
        codes = {item["code"] for item in resp.json()["team_roles"]}
        assert codes == {"MANAGER", "AGENT"}


class TestEntityDeleteStrategiesDictionary:
    """
    entity_delete_strategies es DINÁMICO (app/core/dictionaries.py::get_entity_delete_strategies):
    recorre las subclases de BaseRepository en runtime, no es un dict hardcodeado. Estos tests
    no reimplementan esa misma lógica (sería tautológico) -- verifican la forma de la respuesta
    y comparan contra valores conocidos, tomados directamente de cómo cada repositorio declara
    su `delete_strategy` hoy.
    """

    def _get_strategies(self, client, org_id):
        resp = client.get(
            "/metadata/dictionaries",
            params={"keys": "entity_delete_strategies"},
            headers={"X-Organization-Id": str(org_id)},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["entity_delete_strategies"]

    def test_keys_are_model_class_names_not_entity_codes(self, client, initial_structure):
        strategies = self._get_strategies(client, initial_structure["org_id"])
        # Nombre de clase del modelo ("Lead"), no el código de SYSTEM_ENTITIES_REGISTRY ("lead")
        assert "Lead" in strategies
        assert "lead" not in strategies

    @pytest.mark.parametrize("model_name,expected_strategy", [
        ("Lead", DeleteStrategy.HARD_DELETE_ALWAYS),
        ("Role", DeleteStrategy.SOFT_DELETE_ALWAYS),
        ("Campaign", DeleteStrategy.SOFT_DELETE_HARD_OPT),
        ("Organization", DeleteStrategy.PROTECTED),
        ("Permission", DeleteStrategy.PROTECTED),
        ("LeadField", DeleteStrategy.SMART_DELETE),
        ("Workspace", DeleteStrategy.SMART_DELETE),
        ("LeadRoutingPolicy", DeleteStrategy.HARD_DELETE_WITH_TOGGLE),
        ("FieldAutomation", DeleteStrategy.HARD_DELETE_WITH_TOGGLE),
        ("TeamCampaignAccess", DeleteStrategy.HARD_DELETE_ALWAYS),
        ("TeamWorkspaceAccess", DeleteStrategy.HARD_DELETE_ALWAYS),
    ])
    def test_known_entity_has_expected_strategy(self, client, initial_structure, model_name, expected_strategy):
        strategies = self._get_strategies(client, initial_structure["org_id"])
        assert strategies.get(model_name) == expected_strategy

    def test_all_values_are_known_delete_strategy_variants(self, client, initial_structure):
        """Ningún repo debería exponer un string que no sea una de las 6 variantes válidas."""
        strategies = self._get_strategies(client, initial_structure["org_id"])
        valid = {
            DeleteStrategy.HARD_DELETE_ALWAYS,
            DeleteStrategy.SOFT_DELETE_ALWAYS,
            DeleteStrategy.SOFT_DELETE_HARD_OPT,
            DeleteStrategy.PROTECTED,
            DeleteStrategy.SMART_DELETE,
            DeleteStrategy.HARD_DELETE_WITH_TOGGLE,
        }
        assert strategies, "El diccionario no debería estar vacío"
        assert set(strategies.values()).issubset(valid)
