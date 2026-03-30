import pytest
from sqlalchemy import text, Table, MetaData
from app.models.campaign import Campaign
from app.models.workspace import Workspace
import time

"""

def _get_or_create_secondary_user(db_session):
    #Busca un usuario secundario válido para los tests. Si no hay, clona dinámicamente al usuario 1 para evitar violaciones de Foreign Key.
    
    res = db_session.execute(text('SELECT id FROM "user" WHERE id != 1 LIMIT 1')).scalar()
    if res: return res
        
    metadata = MetaData()
    user_table = Table('user', metadata, autoload_with=db_session.bind)
    user_1 = db_session.execute(user_table.select().limit(1)).mappings().first()
    
    user_dict = dict(user_1)
    user_dict.pop('id', None)
    
    suffix = int(time.time())
    if 'email' in user_dict:
        user_dict['email'] = f'clon_{suffix}@test.com'
        
    db_session.execute(user_table.insert().values(**user_dict))
    db_session.commit()
    
    return db_session.execute(text(f"SELECT id FROM \"user\" WHERE email = 'clon_{suffix}@test.com'")).scalar()


def _set_superuser_status(db_session, user_id: int, status: bool):
    #Enciende o apaga la llave maestra del usuario
    # Descomenta y ajusta el nombre de tu modelo y propiedad
    # user = db_session.get(User, user_id)
    # user.is_superuser = status  <-- Cambia por tu campo real (ej: is_admin, role)
    # db_session.commit()
    
    # Alternativa directa con SQL para no depender de importar el modelo:
    db_session.execute(text(f'UPDATE "user" SET is_superuser = {str(status).lower()} WHERE id = {user_id}'))
    db_session.commit()


def test_security_macro_top_down_and_containment_wall(api, db_session, initial_structure):
    
    #Prueba: Herencia Top-Down y Muro de Contención (Isolation) para un usuario NORMAL.
    
    # 0. APAGAMOS EL MODO SUPER ADMIN PARA EL TEST
    _set_superuser_status(db_session, 1, False)

    flow_id = initial_structure["lead_flow_id"]
    ws_permitido = api.create_workspace("WS Permitido", is_public=False)
    ws_prohibido = api.create_workspace("WS Prohibido", is_public=False)

    camp_permitida = api.create_campaign(ws_permitido["id"], "Campaña Visible", lead_flow_id=flow_id, is_public=False)
    camp_prohibida = api.create_campaign(ws_prohibido["id"], "Campaña Oculta", lead_flow_id=flow_id, is_public=False)

    other_user_id = _get_or_create_secondary_user(db_session)
    db_ws = db_session.get(Workspace, ws_prohibido["id"])
    db_camp = db_session.get(Campaign, camp_prohibida["id"])
    db_ws.created_by = other_user_id
    db_camp.created_by = other_user_id
    db_session.commit()

    team = api.create_team("Equipo Top-Down")
    api.add_team_member(team["id"], user_id=1, role="AGENT")
    api.grant_workspace_access(team["id"], ws_permitido["id"])

    res_list = api.client.get("/campaigns/", headers=api.headers)
    camp_ids = [c["id"] for c in res_list.json().get("items", [])]
    
    assert camp_permitida["id"] in camp_ids, "La herencia Top-Down falló: no ve la campaña hija."
    assert camp_prohibida["id"] not in camp_ids, "Falla de aislamiento: el usuario normal ve una campaña prohibida."

    res_wall = api.client.get(f"/campaigns/{camp_prohibida['id']}", headers=api.headers)
    assert res_wall.status_code == 404, "Muro roto: El usuario normal pudo acceder a una campaña prohibida por ID."

    # Restauramos el estado por las dudas
    _set_superuser_status(db_session, 1, True)


def test_security_macro_bottom_up(api, db_session, initial_structure):
    
    #Prueba: Herencia Bottom-Up para usuario NORMAL.
    
    _set_superuser_status(db_session, 1, False)

    flow_id = initial_structure["lead_flow_id"]
    ws_padre = api.create_workspace("WS Padre Heredado", is_public=False)
    camp_hija = api.create_campaign(ws_padre["id"], "Campaña Hija", lead_flow_id=flow_id, is_public=False)

    other_user_id = _get_or_create_secondary_user(db_session)
    db_ws = db_session.get(Workspace, ws_padre["id"])
    db_ws.created_by = other_user_id
    db_session.commit()

    team = api.create_team("Equipo Bottom-Up")
    api.add_team_member(team["id"], user_id=1, role="AGENT")
    api.grant_campaign_access(team["id"], camp_hija["id"])

    res_ws = api.client.get("/workspaces/", headers=api.headers)
    ws_ids = [w["id"] for w in res_ws.json().get("items", [])]
    assert ws_padre["id"] in ws_ids, "La herencia Bottom-Up falló: no puede ver el Workspace padre."
    
    _set_superuser_status(db_session, 1, True)


def test_security_micro_manager_vs_strict_agent(api, db_session, initial_structure):
    
    #Prueba: Visibilidad MICRO (Ojo del Manager vs Agente Estricto) para usuario NORMAL.
    
    _set_superuser_status(db_session, 1, False)

    flow_id = initial_structure["lead_flow_id"]
    ws = api.create_workspace("WS Ventas", is_public=False)
    camp = api.create_campaign(ws["id"], "Ventas 2026", lead_flow_id=flow_id, is_public=False)

    team_strict = api.create_team("Equipo Estricto", is_visibility_shared=False)
    api.grant_workspace_access(team_strict["id"], ws["id"])

    member = api.add_team_member(team_strict["id"], user_id=1, role="AGENT")

    f_base = api.create_lead_field(camp["id"], "Dato", "STRING")
    
    lead_mio = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead del Usuario 1"}])
    lead_huerfano = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead sin dueño"}])
    lead_vecino = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead del Compañero"}])

    other_user_id = _get_or_create_secondary_user(db_session)

    api.bulk_assign([lead_mio["id"]], target_team_id=team_strict["id"], target_user_id=1)
    api.bulk_assign([lead_huerfano["id"]], target_team_id=team_strict["id"], target_user_id=None)
    api.bulk_assign([lead_vecino["id"]], target_team_id=team_strict["id"], target_user_id=other_user_id) 

    # VISTA DE AGENTE
    res_agent = api.client.get(f"/leads/?campaign_id={camp['id']}", headers=api.headers)
    leads_agent = [l["id"] for l in res_agent.json().get("items", [])]

    assert lead_mio["id"] in leads_agent
    assert lead_huerfano["id"] in leads_agent
    assert lead_vecino["id"] not in leads_agent, "Falla de seguridad: El Agente estricto puede ver el lead de su compañero."

    # ASCENSO A MANAGER
    api.client.put(f"/team_members/{member['id']}", json={"role": "MANAGER"}, headers=api.headers)

    # VISTA DE MANAGER
    res_mgr = api.client.get(f"/leads/?campaign_id={camp['id']}", headers=api.headers)
    leads_mgr = [l["id"] for l in res_mgr.json().get("items", [])]

    assert lead_vecino["id"] in leads_mgr, "El Manager no puede ver los leads de sus subordinados."
    
    _set_superuser_status(db_session, 1, True)


def test_security_super_admin_bypass(api, db_session, initial_structure):
    
    #Prueba: El Super Admin ignora la Bóveda y ve absolutamente TODO, sin pertenecer a ningún equipo.
    # 1. ENCENDEMOS LA LLAVE MAESTRA
    _set_superuser_status(db_session, 1, True)

    flow_id = initial_structure["lead_flow_id"]
    ws_secreto = api.create_workspace("WS Area 51", is_public=False)
    camp_secreta = api.create_campaign(ws_secreto["id"], "Campaña Top Secret", lead_flow_id=flow_id, is_public=False)

    # Simulamos que son propiedad de otro usuario y nosotros no estamos en ningún equipo
    other_user_id = _get_or_create_secondary_user(db_session)
    db_ws = db_session.get(Workspace, ws_secreto["id"])
    db_camp = db_session.get(Campaign, camp_secreta["id"])
    db_ws.created_by = other_user_id
    db_camp.created_by = other_user_id
    db_session.commit()

    # --- VERIFICACIÓN SUPER ADMIN ---
    res_list = api.client.get("/campaigns/", headers=api.headers)
    assert res_list.status_code == 200
    
    camp_ids = [c["id"] for c in res_list.json().get("items", [])]
    
    assert camp_secreta["id"] in camp_ids, "El Super Admin NO pudo ver la campaña privada de otro usuario."

    res_direct = api.client.get(f"/campaigns/{camp_secreta['id']}", headers=api.headers)
    assert res_direct.status_code == 200, "El Super Admin fue bloqueado por el muro 404."


"""