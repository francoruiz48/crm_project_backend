import requests
import random
from datetime import datetime
from faker import Faker

# --- CONFIGURACIÓN ---
BASE_URL = "http://localhost:8000"
LOCALE = 'es_AR'

fake = Faker(LOCALE)
session = requests.Session()
# session.headers.update({"Authorization": "Bearer ..."}) # Descomentar cuando haya seguridad

# --- HELPERS API (CRUD) ---

def log(msg, success=True):
    symbol = "✅" if success else "❌"
    print(f"{symbol} {msg}")

def get_nomenclator_items(nomenclator_id):
    """Trae items completos (para lógica Pais/Provincia)"""
    try:
        url = f"{BASE_URL}/nomenclator_items/?nomenclator_id={nomenclator_id}&only_active=True&page_size=300"
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            # Soporte para respuesta paginada o lista directa
            items = data.get("items", []) if isinstance(data, dict) else data
            return items
    except Exception:
        pass
    return []

def create_workspace(name):
    resp = session.post(f"{BASE_URL}/workspaces/", json={"name": name, "description": fake.catch_phrase()})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    print(f"Error Workspace: {resp.text}")
    return None

def create_campaign(name, workspace_id):
    resp = session.post(f"{BASE_URL}/campaigns/", json={"name": name, "description": fake.catch_phrase(), "workspace_id": workspace_id, "active": True})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    print(f"Error Campaña: {resp.text}")
    return None

def create_field(campaign_id, name=None, type_code=None, template_code=None, required=False, nom_id=None, order=1):
    payload = {
        "campaign_id": campaign_id,
        "required": required,
        "is_primary": False,
        "order": order
    }
    
    if template_code:
        payload["field_template_code"] = template_code
    else:
        if nom_id:
            payload["nomenclator_id"] = nom_id
        else:
            payload["name"] = name
            payload["field_type_code"] = type_code

    resp = session.post(f"{BASE_URL}/lead_fields/", json=payload)
    if resp.status_code in [200, 201]:
        return resp.json()['id'], name
    print(f"Error Field {name}: {resp.text}")
    return None, None

def create_lead(campaign_id, values):
    resp = session.post(f"{BASE_URL}/leads/", json={"campaign_id": campaign_id, "values": values})
    return resp.status_code in [200, 201]

# --- LÓGICA DE NEGOCIO ---

def setup_campaign_fields(campaign_id, province_data_available):
    """
    Crea los campos obligatorios y selecciona un mix aleatorio de opcionales.
    Devuelve un diccionario 'mapa de campos'.
    """
    fields_map = {}
    order_counter = 1

    # 1. CAMPOS FIJOS (Siempre están)
    fid, _ = create_field(campaign_id, template_code="FIRST_NAME", required=True, order=order_counter)
    fields_map["nombre"] = fid
    order_counter += 1

    fid, _ = create_field(campaign_id, template_code="LAST_NAME", required=True, order=order_counter)
    fields_map["apellido"] = fid
    order_counter += 1

    # 2. POOL DE CAMPOS OPCIONALES
    # Definimos posibles configuraciones de campos adicionales
    optional_pool = [
        {"key": "dni", "template": "DNI_ARG", "req": True},
        {"key": "email", "name": "Email Personal", "type": "STRING", "req": False}, # Asumimos String, si tienes type EMAIL usalo
        {"key": "telefono", "name": "Teléfono", "type": "STRING", "req": False},
        {"key": "nacimiento", "template": "BIRTH_DATE", "req": False},
        {"key": "presupuesto", "name": "Presupuesto USD", "type": "INT", "req": False},
        {"key": "es_vip", "name": "Cliente VIP", "type": "BOOL", "req": False},
        {"key": "notas", "name": "Notas Adicionales", "type": "STRING", "req": False}
    ]

    # Si hay provincias cargadas, agregamos la "Ubicación" como opción posible
    if province_data_available:
        optional_pool.append({"key": "ubicacion_combo", "is_combo": True})

    # Elegimos al azar 3 o 4 opciones del pool para esta campaña
    selected_options = random.sample(optional_pool, k=random.randint(3, 5))

    for opt in selected_options:
        if opt.get("is_combo"):
            # Crear País y Provincia
            fid_p, _ = create_field(campaign_id, name="Pais", nom_id=1, required=True, order=order_counter)
            fields_map["pais"] = fid_p
            order_counter += 1
            
            fid_pr, _ = create_field(campaign_id, name="Provincia", nom_id=2, required=True, order=order_counter)
            fields_map["provincia"] = fid_pr
            order_counter += 1
        else:
            # Crear campo normal
            fid, _ = create_field(
                campaign_id, 
                name=opt.get("name"), 
                type_code=opt.get("type"), 
                template_code=opt.get("template"), 
                required=opt["req"], 
                order=order_counter
            )
            fields_map[opt["key"]] = fid
            order_counter += 1

    return fields_map

def generate_leads_for_campaign(campaign_id, fields_map, count, provincias_data):
    print(f"   ↳ Generando {count} leads...")
    
    for _ in range(count):
        lead_values = []

        # -- Obligatorios --
        lead_values.append({"field_id": fields_map["nombre"], "value": fake.first_name()})
        lead_values.append({"field_id": fields_map["apellido"], "value": fake.last_name()})

        # -- Opcionales (Solo si la campaña tiene el campo) --
        
        if "dni" in fields_map:
            lead_values.append({"field_id": fields_map["dni"], "value": str(fake.unique.random_number(digits=8, fix_len=True))})
        
        if "email" in fields_map:
            lead_values.append({"field_id": fields_map["email"], "value": fake.free_email()})
            
        if "telefono" in fields_map:
            lead_values.append({"field_id": fields_map["telefono"], "value": fake.phone_number()})

        if "nacimiento" in fields_map:
            date_val = fake.date_between(start_date='-60y', end_date='-20y')
            lead_values.append({"field_id": fields_map["nacimiento"], "value": str(date_val)})

        if "presupuesto" in fields_map:
            lead_values.append({"field_id": fields_map["presupuesto"], "value": str(random.randint(1000, 50000))})

        if "es_vip" in fields_map:
            lead_values.append({"field_id": fields_map["es_vip"], "value": random.choice(["true", "false"])})
            
        if "notas" in fields_map:
            lead_values.append({"field_id": fields_map["notas"], "value": fake.sentence()})

        # -- Lógica Combo Pais/Provincia --
        if "provincia" in fields_map and "pais" in fields_map and provincias_data:
            prov = random.choice(provincias_data)
            if prov.get('parent_item_id'):
                lead_values.append({"field_id": fields_map["provincia"], "nomenclator_item_id": prov['id']})
                lead_values.append({"field_id": fields_map["pais"], "nomenclator_item_id": prov['parent_item_id']})

        # Enviar
        create_lead(campaign_id, lead_values)

# --- EJECUCIÓN PRINCIPAL ---

def run_seed():
    print("\n--- 🚀 Iniciando Seeding Masivo ---")

    # 1. Obtener Datos Auxiliares
    # Asumimos ID 2 = Provincias. Si no existe, los campos de ubicación no se crearán.
    provincias_data = get_nomenclator_items(2)
    
    # -------------------------------------------------------------
    # ESCENARIO A: Workspace "Ventas Corporativas" (3 Campañas)
    # -------------------------------------------------------------
    ws1_id = create_workspace("Ventas Corporativas")
    if ws1_id:
        log(f"Workspace creado: Ventas Corporativas (ID: {ws1_id})")
        
        # Crear 3 campañas variadas
        for i in range(1, 4):
            camp_name = f"Campaña {fake.bs().title()} {datetime.now().year}"
            camp_id = create_campaign(camp_name, ws1_id)
            
            if camp_id:
                # Configurar campos únicos para esta campaña
                f_map = setup_campaign_fields(camp_id, bool(provincias_data))
                
                # Generar leads (Entre 50 y 500)
                qty = random.randint(50, 500)
                log(f"Campaña '{camp_name}' configurada con {len(f_map)} campos. Generando {qty} leads.")
                generate_leads_for_campaign(camp_id, f_map, qty, provincias_data)

    # -------------------------------------------------------------
    # ESCENARIO B: Workspace "Marketing" (1 Campaña)
    # -------------------------------------------------------------
    ws2_id = create_workspace("Marketing Digital")
    if ws2_id:
        log(f"Workspace creado: Marketing Digital (ID: {ws2_id})")
        
        camp_name = "Leads Inbound Q1"
        camp_id = create_campaign(camp_name, ws2_id)
        
        if camp_id:
            f_map = setup_campaign_fields(camp_id, bool(provincias_data))
            qty = random.randint(100, 300)
            log(f"Campaña '{camp_name}' configurada. Generando {qty} leads.")
            generate_leads_for_campaign(camp_id, f_map, qty, provincias_data)

    print("\n--- ✅ Proceso Finalizado Exitosamente ---")

if __name__ == "__main__":
    run_seed()