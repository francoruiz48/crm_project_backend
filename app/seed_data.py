import requests
import random
from datetime import datetime
from faker import Faker

# --- CONFIGURACIÓN ---
BASE_URL = "http://localhost:8000"
LOCALE = 'es_AR'

fake = Faker(LOCALE)
session = requests.Session()

# --- HELPERS API (CRUD) ---

def log(msg, success=True):
    symbol = "✅" if success else "❌"
    print(f"{symbol} {msg}")

def get_nomenclator_items(nomenclator_id):
    try:
        url = f"{BASE_URL}/nomenclator_items/?nomenclator_id={nomenclator_id}&only_active=True&page_size=300"
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else data
            return items
    except Exception:
        pass
    return []

def create_lead_field_section(name):
    """Crea una sección y devuelve su ID"""
    resp = session.post(f"{BASE_URL}/lead_field_sections/", json={"name": name})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    # Si ya existe o falla, intentamos manejarlo (o simplemente imprimir error)
    print(f"Nota Section {name}: {resp.text}") 
    return None

def create_workspace(name):
    resp = session.post(f"{BASE_URL}/workspaces/", json={"name": name, "description": fake.catch_phrase()})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    return None

def create_campaign(name, workspace_id):
    resp = session.post(f"{BASE_URL}/campaigns/", json={"name": name, "description": fake.catch_phrase(), "workspace_id": workspace_id, "active": True})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    return None

def create_field(campaign_id, section_id, name=None, type_code=None, template_code=None, required=False, nom_id=None, order=1):
    """
    Ahora recibe section_id obligatoriamente.
    """
    payload = {
        "campaign_id": campaign_id,
        "lead_field_section_id": section_id,
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

def setup_campaign_fields(campaign_id, sections_ids, province_data_available):
    """
    Configura los campos distribuidos en las 3 secciones.
    """
    fields_map = {}
    order_counter = 1

    # ---------------------------------------------------------
    # SECCIÓN 1: DATOS PERSONALES (Fijos)
    # ---------------------------------------------------------
    sec_personal = sections_ids["Datos Personales"]
    
    # Nombre
    fid, _ = create_field(campaign_id, sec_personal, template_code="FIRST_NAME", required=True, order=1)
    fields_map["nombre"] = fid
    
    # Apellido
    fid, _ = create_field(campaign_id, sec_personal, template_code="LAST_NAME", required=True, order=2)
    fields_map["apellido"] = fid
    
    # DNI (Global ID)
    fid, _ = create_field(campaign_id, sec_personal, template_code="DNI_ARG", required=True, order=3)
    fields_map["dni"] = fid

    # ---------------------------------------------------------
    # SECCIÓN 2: INFORMACIÓN DE CONTACTO (Fijos)
    # ---------------------------------------------------------
    sec_contact = sections_ids["Información de Contacto"]
    
    # Email
    fid, _ = create_field(campaign_id, sec_contact, name="Email", type_code="STRING", required=False, order=1)
    fields_map["email"] = fid
    
    # Teléfono
    fid, _ = create_field(campaign_id, sec_contact, name="Teléfono", type_code="STRING", required=False, order=2)
    fields_map["telefono"] = fid
    
    # Dirección
    fid, _ = create_field(campaign_id, sec_contact, name="Dirección", type_code="STRING", required=False, order=3)
    fields_map["direccion"] = fid

    # ---------------------------------------------------------
    # SECCIÓN 3: DETALLES ADICIONALES (Variables)
    # ---------------------------------------------------------
    sec_extra = sections_ids["Detalles Adicionales"]
    
    # Pool de opciones aleatorias
    optional_pool = [
        {"key": "nacimiento", "template": "BIRTH_DATE", "req": False},
        {"key": "presupuesto", "name": "Presupuesto USD", "type": "INT", "req": False},
        {"key": "es_vip", "name": "Cliente VIP", "type": "BOOL", "req": False},
        {"key": "notas", "name": "Notas de Interés", "type": "STRING", "req": False},
        {"key": "origen", "name": "Origen del Lead", "type": "STRING", "req": False}
    ]

    if province_data_available:
        optional_pool.append({"key": "ubicacion_combo", "is_combo": True})

    # Elegimos 3 variables random para esta campaña
    selected_options = random.sample(optional_pool, k=3)
    extra_order = 1

    for opt in selected_options:
        if opt.get("is_combo"):
            # País y Provincia
            fid_p, _ = create_field(campaign_id, sec_extra, nom_id=1, required=True, order=extra_order)
            fields_map["pais"] = fid_p
            extra_order += 1
            
            fid_pr, _ = create_field(campaign_id, sec_extra, nom_id=2, required=True, order=extra_order)
            fields_map["provincia"] = fid_pr
            extra_order += 1
        else:
            fid, _ = create_field(
                campaign_id, 
                sec_extra,
                name=opt.get("name"), 
                type_code=opt.get("type"), 
                template_code=opt.get("template"), 
                required=opt["req"], 
                order=extra_order
            )
            fields_map[opt["key"]] = fid
            extra_order += 1

    return fields_map

def generate_leads_for_campaign(campaign_id, fields_map, count, provincias_data):
    print(f"   ↳ Generando {count} leads...")
    
    for _ in range(count):
        lead_values = []

        # --- SECCIÓN 1: DATOS PERSONALES ---
        lead_values.append({"field_id": fields_map["nombre"], "value": fake.first_name()})
        lead_values.append({"field_id": fields_map["apellido"], "value": fake.last_name()})
        lead_values.append({"field_id": fields_map["dni"], "value": str(fake.unique.random_number(digits=8, fix_len=True))})

        # --- SECCIÓN 2: CONTACTO ---
        if "email" in fields_map:
            lead_values.append({"field_id": fields_map["email"], "value": fake.free_email()})
        if "telefono" in fields_map:
            lead_values.append({"field_id": fields_map["telefono"], "value": fake.phone_number()})
        if "direccion" in fields_map:
            lead_values.append({"field_id": fields_map["direccion"], "value": fake.address()})

        # --- SECCIÓN 3: VARIABLES ---
        if "nacimiento" in fields_map:
            date_val = fake.date_between(start_date='-60y', end_date='-20y')
            lead_values.append({"field_id": fields_map["nacimiento"], "value": str(date_val)})

        if "presupuesto" in fields_map:
            lead_values.append({"field_id": fields_map["presupuesto"], "value": str(random.randint(1000, 50000))})

        if "es_vip" in fields_map:
            lead_values.append({"field_id": fields_map["es_vip"], "value": random.choice(["true", "false"])})
            
        if "notas" in fields_map:
            lead_values.append({"field_id": fields_map["notas"], "value": fake.sentence()})
            
        if "origen" in fields_map:
            lead_values.append({"field_id": fields_map["origen"], "value": random.choice(["Facebook", "Instagram", "Google", "Referido"])})

        # Lógica Combo
        if "provincia" in fields_map and "pais" in fields_map and provincias_data:
            prov = random.choice(provincias_data)
            if prov.get('parent_item_id'):
                lead_values.append({"field_id": fields_map["provincia"], "nomenclator_item_id": prov['id']})
                lead_values.append({"field_id": fields_map["pais"], "nomenclator_item_id": prov['parent_item_id']})

        create_lead(campaign_id, lead_values)

# --- EJECUCIÓN PRINCIPAL ---

def run_seed():
    print("\n--- 🚀 Iniciando Seeding V3 ---")

    # 1. Obtener Datos Auxiliares
    provincias_data = get_nomenclator_items(2)

    # 2. Crear las Secciones (Una sola vez o asegurando IDs)
    print("--- Creando Secciones Globales ---")
    sections_ids = {
        "Datos Personales": create_lead_field_section("Datos Personales"),
        "Información de Contacto": create_lead_field_section("Información de Contacto"),
        "Detalles Adicionales": create_lead_field_section("Detalles Adicionales")
    }
    
    # Validamos que se crearon las secciones
    if None in sections_ids.values():
        print("⚠️ Algunas secciones no se crearon (quizás ya existen). Usando IDs asumidos 1, 2, 3 si falló la creación.")
        # Fallback simple si el script corre sobre DB sucia
        if not sections_ids["Datos Personales"]: sections_ids["Datos Personales"] = 1
        if not sections_ids["Información de Contacto"]: sections_ids["Información de Contacto"] = 2
        if not sections_ids["Detalles Adicionales"]: sections_ids["Detalles Adicionales"] = 3

    # -------------------------------------------------------------
    # ESCENARIO A: Workspace "Ventas Corporativas" (3 Campañas)
    # -------------------------------------------------------------
    ws1_id = create_workspace("Ventas Corporativas")
    if ws1_id:
        log(f"Workspace creado: Ventas Corporativas (ID: {ws1_id})")
        
        for i in range(1, 4):
            camp_name = f"Campaña {fake.bs().title()} {datetime.now().year}"
            camp_id = create_campaign(camp_name, ws1_id)
            
            if camp_id:
                f_map = setup_campaign_fields(camp_id, sections_ids, bool(provincias_data))
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
            f_map = setup_campaign_fields(camp_id, sections_ids, bool(provincias_data))
            qty = random.randint(100, 300)
            log(f"Campaña '{camp_name}' configurada. Generando {qty} leads.")
            generate_leads_for_campaign(camp_id, f_map, qty, provincias_data)

    print("\n--- ✅ Proceso Finalizado ---")

if __name__ == "__main__":
    run_seed()