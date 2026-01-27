import requests
import random
from datetime import datetime, timedelta
from faker import Faker

# --- CONFIGURACIÓN ---
BASE_URL = "http://localhost:8000"
LOCALE = 'es_AR'

fake = Faker(LOCALE)
session = requests.Session()

# --- CONSTANTES ---
TYPES = {
    "SELECTOR": "SELECTOR",
    "CHECKBOX": "CHECKBOX",
    "MONEY": "MONEY",
    "URL": "URL",
    "PHONE": "PHONE",
    "RATING": "RATING",
    "ADDRESS": "ADDRESS",
    "EMAIL": "EMAIL"
}

SUBTYPES = {
    "SEL_SINGLE": "SELECTOR_SIMPLE",
    "SEL_MULTI": "SELECTOR_MULTIPLE",
    "CHK_SINGLE": "CHECKBOX_SIMPLE",
    "CHK_MULTI": "CHECKBOX_MULTIPLE",
    "URL_WEB": "WEBSITE",
    "PHONE_MOB": "MOBILE",
    "RATING_STARS": "STAR_RATING",
    "ADDR_COORDS": "COORDINATES"
}

# --- HELPERS API ---

def log(msg, success=True):
    symbol = "✅" if success else "❌"
    print(f"{symbol} {msg}")

def get_nomenclator_items(nomenclator_id):
    try:
        url = f"{BASE_URL}/nomenclator_items?nomenclator_id={nomenclator_id}&only_active=True&page_size=300"
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"⚠️ Error obteniendo nomenclador {nomenclator_id}: {e}")
    return []

def get_leads_ids(campaign_id):
    try:
        url = f"{BASE_URL}/leads/?campaign_id={campaign_id}&page=1&page_size=500"
        resp = session.get(url)
        
        if resp.status_code != 200:
            print(f"⚠️ Error GET Leads (Camp {campaign_id}): {resp.status_code} {resp.text}")
            return []

        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        ids = [l['id'] for l in items]
        print(f"   ℹ️ IDs recuperados para relaciones: {len(ids)}")
        return ids

    except Exception as e:
        print(f"⚠️ Excepción en get_leads_ids: {e}")
        return []

def get_lead_field_section(name):
    try:
        resp = session.get(f"{BASE_URL}/lead_field_sections?name={name}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', []) if isinstance(data, dict) else data
            if items: return items[0]['id']
        
        resp = session.post(f"{BASE_URL}/lead_field_sections/", json={"name": name})
        if resp.status_code in [200, 201]:
            return resp.json()['id']
    except Exception:
        pass
    return 1

def create_organization(name, description=None):
    resp = session.post(f"{BASE_URL}/organizations/", json={"name": name, "description": description})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    print(f"❌ Error creando Organization: {resp.text}")
    return None

def create_workspace(name, organization_id):
    resp = session.post(f"{BASE_URL}/workspaces/", json={"name": name, "description": "Auto Generated", "organization_id": organization_id})
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    print(f"❌ Error creando Workspace: {resp.text}")
    return None

def create_campaign(name, workspace_id):
    payload = {
        "name": name, 
        "description": "Seed Data Campaign", 
        "workspace_id": workspace_id, 
        "active": True
    }
    resp = session.post(f"{BASE_URL}/campaigns/", json=payload)
    if resp.status_code in [200, 201]:
        return resp.json()['id']
    
    print(f"❌ Error creando Campaña '{name}': {resp.text}")
    return None

def create_field(campaign_id, section_id, name=None, type_code=None, subtype_code=None, 
                 template_code=None, required=False, nom_id=None, 
                 expression=None, related_camp_id=None):
    
    payload = {
        "campaign_id": campaign_id,
        "lead_field_section_id": section_id,
        "required": required,
        "is_primary": False,
        "is_visible": True
    }
    
    if template_code:
        payload["field_template_code"] = template_code
    else:
        payload["name"] = name
        payload["field_type_code"] = type_code
        if subtype_code:
            payload["field_subtype_code"] = subtype_code
        
        if nom_id:
            payload["nomenclator_id"] = nom_id
        
        if expression:
            payload["calculation_expression"] = expression
            
        if related_camp_id:
            payload["related_campaign_id"] = related_camp_id

    resp = session.post(f"{BASE_URL}/lead_fields/", json=payload)
    if resp.status_code in [200, 201]:
        return resp.json()['id'], resp.json()['name']
    
    print(f"⚠️ Error Field '{name or template_code}': {resp.text}")
    return None, None

def create_lead(campaign_id, values):
    clean_values = [v for v in values if v.get("field_id") is not None]
    if not clean_values: return False

    payload = {"campaign_id": campaign_id, "values": clean_values}
    resp = session.post(f"{BASE_URL}/leads/", json=payload)
    
    if resp.status_code not in [200, 201]:
        pass
    return resp.status_code in [200, 201]

# --- SETUP CAMPAÑAS ---

def setup_base_campaign(campaign_id, sections):
    f_map = {}
    f_map["nombre"], _ = create_field(campaign_id, sections["Personal"], template_code="FIRST_NAME", required=True)
    f_map["apellido"], _ = create_field(campaign_id, sections["Personal"], template_code="LAST_NAME", required=True)
    f_map["dni"], _ = create_field(campaign_id, sections["Personal"], template_code="DNI_ARG", required=True)
    
    # CAMBIO: Usamos el tipo EMAIL nativo, no STRING
    f_map["email"], _ = create_field(campaign_id, sections["Detalles"], name="Email Personal", type_code=TYPES["EMAIL"])
    
    return f_map

def setup_complex_campaign(campaign_id, sections):
    f_map = {}
    # Fechas
    f_map["fecha_nac"], _ = create_field(campaign_id, sections["Personal"], template_code="BIRTH_DATE")
    
    # --- NUEVOS TIPOS DE DATOS ---
    f_map["presupuesto"], _ = create_field(campaign_id, sections["Detalles"], name="Presupuesto Estimado", type_code=TYPES["MONEY"])
    
    f_map["website"], _ = create_field(campaign_id, sections["Detalles"], name="Sitio Web", 
                                       type_code=TYPES["URL"], subtype_code=SUBTYPES["URL_WEB"])
    
    f_map["celular"], _ = create_field(campaign_id, sections["Personal"], name="Teléfono Móvil", 
                                       type_code=TYPES["PHONE"], subtype_code=SUBTYPES["PHONE_MOB"])
    
    f_map["calificacion"], _ = create_field(campaign_id, sections["Detalles"], name="Nivel de Interés", 
                                            type_code=TYPES["RATING"], subtype_code=SUBTYPES["RATING_STARS"])
    
    f_map["ubicacion"], _ = create_field(campaign_id, sections["Detalles"], name="Ubicación GPS", 
                                         type_code=TYPES["ADDRESS"], subtype_code=SUBTYPES["ADDR_COORDS"])

    # Nomencladores
    f_map["pais_sel"], _ = create_field(campaign_id, sections["Combos"], name="País (Selector)", 
                                        type_code=TYPES["SELECTOR"], subtype_code=SUBTYPES["SEL_SINGLE"], nom_id=1)
    
    f_map["prov_multi"], _ = create_field(campaign_id, sections["Combos"], name="Provincias Interés (Multi-Sel)", 
                                          type_code=TYPES["SELECTOR"], subtype_code=SUBTYPES["SEL_MULTI"], nom_id=2)

    return f_map

def setup_calculated_campaign(campaign_id, sections):
    f_map = {}
    f_map["precio"], name_precio = create_field(campaign_id, sections["Detalles"], name="Precio Unitario", type_code="NUMBER")
    f_map["cantidad"], name_cant = create_field(campaign_id, sections["Detalles"], name="Cantidad", type_code="INT")
    
    if name_precio and name_cant:
        formula = f"= {name_precio} * {name_cant}"
        f_map["total"], _ = create_field(campaign_id, sections["Detalles"], name="Total (Calc)", 
                                         type_code="CALCULATED", expression=formula)
    return f_map

def setup_relational_campaign(campaign_id, target_campaign_id, sections):
    f_map = {}
    f_map["nombre"], _ = create_field(campaign_id, sections["Personal"], template_code="FIRST_NAME")
    f_map["referido_por"], _ = create_field(campaign_id, sections["Detalles"], name="Cliente Referido (Lead)", 
                                            type_code="LEAD", related_camp_id=target_campaign_id)
    return f_map

# --- DATA GEN ---

def generate_data(campaign_id, f_map, count, nom_data, target_leads_ids=None):
    if not campaign_id: return
    print(f"   ↳ Generando {count} leads...")
    
    paises = nom_data.get('paises', [])
    provincias = nom_data.get('provincias', [])
    
    for _ in range(count):
        values = []
        
        # Datos Básicos
        if f_map.get("nombre"): values.append({"field_id": f_map["nombre"], "value": fake.first_name()})
        if f_map.get("apellido"): values.append({"field_id": f_map["apellido"], "value": fake.last_name()})
        if f_map.get("dni"): values.append({"field_id": f_map["dni"], "value": str(fake.unique.random_number(digits=8))})
        if f_map.get("email"): values.append({"field_id": f_map["email"], "value": fake.email()})
        
        # Fechas
        if f_map.get("fecha_nac"): values.append({"field_id": f_map["fecha_nac"], "value": fake.date_of_birth().isoformat()})
        
        # --- GENERACIÓN NUEVOS TIPOS ---
        if f_map.get("presupuesto"): 
            # Money: número float o int (ej: 1500.50)
            values.append({"field_id": f_map["presupuesto"], "value": round(random.uniform(500, 50000), 2)})
            
        if f_map.get("website"): 
            values.append({"field_id": f_map["website"], "value": fake.url()})
            
        if f_map.get("celular"): 
            # Formato simple para pasar validaciones básicas si las hay (+549...)
            phone_val = f"+54 9 {fake.msisdn()[3:]}" 
            values.append({"field_id": f_map["celular"], "value": phone_val})
            
        if f_map.get("calificacion"): 
            # Star Rating es 1-5
            values.append({"field_id": f_map["calificacion"], "value": random.randint(1, 5)})
            
        if f_map.get("ubicacion"): 
            # Coordinates "lat, long"
            coords = f"{fake.latitude()}, {fake.longitude()}"
            values.append({"field_id": f_map["ubicacion"], "value": coords})

        # Cálculos (Inputs)
        if f_map.get("precio"): values.append({"field_id": f_map["precio"], "value": round(random.uniform(10.5, 999.9), 2)})
        if f_map.get("cantidad"): values.append({"field_id": f_map["cantidad"], "value": random.randint(1, 50)})

        # Nomencladores
        if paises:
            pais_rnd = random.choice(paises)['id']
            if f_map.get("pais_sel"): values.append({"field_id": f_map["pais_sel"], "value": pais_rnd})

        if provincias:
            provs_rnd = random.sample(provincias, k=random.randint(1, 3))
            provs_ids = [p['id'] for p in provs_rnd]
            if f_map.get("prov_multi"): values.append({"field_id": f_map["prov_multi"], "value": provs_ids})

        # Relaciones
        if target_leads_ids and f_map.get("referido_por"):
            related = random.sample(target_leads_ids, k=random.randint(1, 2))
            values.append({"field_id": f_map["referido_por"], "value": related})

        create_lead(campaign_id, values)

# --- RUN ---

def run_seed():
    print("\n--- 🚀 SEEDING MASTER V7 (Tipos Avanzados) ---")
    
    sections = {
        "Personal": get_lead_field_section("Datos Personales"),
        "Detalles": get_lead_field_section("Detalles de Venta"),
        "Combos": get_lead_field_section("Clasificación")
    }
    
    nom_data = {
        'paises': get_nomenclator_items(1),
        'provincias': get_nomenclator_items(2)
    }

    if not nom_data['paises']: print("⚠️ Advertencia: Nomenclador 1 (Países) vacío.")
    if not nom_data['provincias']: print("⚠️ Advertencia: Nomenclador 2 (Provincias) vacío.")

    org_id = create_organization("Empresa Demo")

    ws_id = create_workspace(f"Demo Full {datetime.now().strftime('%H:%M:%S')}", org_id)
    if not ws_id: return

    log(f"Workspace creado: ID {ws_id}")

    # 1. BASE
    camp_base_id = create_campaign("1. Base Contactos", ws_id)
    if camp_base_id:
        map_base = setup_base_campaign(camp_base_id, sections)
        generate_data(camp_base_id, map_base, random.randint(60, 120), nom_data)
        log("Campaña Base generada")
    
    # 2. COMPLEJA (Con Money, Rating, Phone, etc)
    camp_complex_id = create_campaign("2. Oportunidades (Avanzado)", ws_id)
    if camp_complex_id:
        map_complex = setup_complex_campaign(camp_complex_id, sections)
        generate_data(camp_complex_id, map_complex, random.randint(60, 100), nom_data)
        log("Campaña Avanzada generada")

    # 3. CALCULOS
    camp_calc_id = create_campaign("3. Presupuestos (Calc)", ws_id)
    if camp_calc_id:
        map_calc = setup_calculated_campaign(camp_calc_id, sections)
        generate_data(camp_calc_id, map_calc, random.randint(10, 80), nom_data)
        log("Campaña Calculada generada")

    # 4. RELACIONES
    base_leads_ids = get_leads_ids(camp_base_id) if camp_base_id else []
    if base_leads_ids:
        camp_rel_id = create_campaign("4. Referidos (Relacional)", ws_id)
        if camp_rel_id:
            map_rel = setup_relational_campaign(camp_rel_id, camp_base_id, sections)
            generate_data(camp_rel_id, map_rel, random.randint(10, 20), nom_data, target_leads_ids=base_leads_ids)
            log("Campaña Relacional generada")
    else:
        log("Saltando Campaña Relacional (faltan leads base)", False)

    print("\n--- ✅ SEED COMPLETADO ---")

if __name__ == "__main__":
    run_seed()