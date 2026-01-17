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
    "CHECKBOX": "CHECKBOX"
}

SUBTYPES = {
    "SEL_SINGLE": "SELECTOR_SIMPLE",
    "SEL_MULTI": "SELECTOR_MULTIPLE",
    "CHK_SINGLE": "CHECKBOX_SIMPLE",
    "CHK_MULTI": "CHECKBOX_MULTIPLE"
}

# --- HELPERS API ---

def log(msg, success=True):
    symbol = "✅" if success else "❌"
    print(f"{symbol} {msg}")

def get_nomenclator_items(nomenclator_id):
    try:
        url = f"{BASE_URL}/nomenclator_items/?nomenclator_id={nomenclator_id}&only_active=True&page_size=300"
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"⚠️ Error obteniendo nomenclador {nomenclator_id}: {e}")
    return []

def get_leads_ids(campaign_id):
    """
    Obtiene los IDs de los leads creados. 
    CORREGIDO: page_size ajustado a 500 para evitar error 422 (Max 999).
    """
    try:
        # CORRECCIÓN AQUÍ: 500 en lugar de 1000
        url = f"{BASE_URL}/leads/?campaign_id={campaign_id}&page=1&page_size=500"
        resp = session.get(url)
        
        if resp.status_code != 200:
            print(f"⚠️ Error GET Leads (Camp {campaign_id}): {resp.status_code} {resp.text}")
            return []

        data = resp.json()
        
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        
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

def create_workspace(name):
    resp = session.post(f"{BASE_URL}/workspaces/", json={"name": name, "description": "Auto Generated"})
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
        "is_visible": True,
        "order": random.randint(1, 100)
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
        # Reducir ruido si es error de validación esperado
        # print(f"Error Lead: {resp.text}")
        pass
    return resp.status_code in [200, 201]

# --- SETUP CAMPAÑAS ---

def setup_base_campaign(campaign_id, sections):
    f_map = {}
    f_map["nombre"], _ = create_field(campaign_id, sections["Personal"], template_code="FIRST_NAME", required=True)
    f_map["apellido"], _ = create_field(campaign_id, sections["Personal"], template_code="LAST_NAME", required=True)
    f_map["dni"], _ = create_field(campaign_id, sections["Personal"], template_code="DNI_ARG", required=True)
    f_map["email"], _ = create_field(campaign_id, sections["Detalles"], name="Email Personal", type_code="STRING")
    return f_map

def setup_complex_campaign(campaign_id, sections):
    f_map = {}
    # Fechas
    f_map["fecha_nac"], _ = create_field(campaign_id, sections["Personal"], template_code="BIRTH_DATE")
    f_map["fecha_evento"], _ = create_field(campaign_id, sections["Detalles"], name="Fecha Evento", type_code="DATE")
    f_map["hora_cita"], _ = create_field(campaign_id, sections["Detalles"], name="Hora Cita", type_code="DATE_TIME")

    # Nomencladores
    f_map["pais_sel"], _ = create_field(campaign_id, sections["Combos"], name="País (Selector)", 
                                        type_code=TYPES["SELECTOR"], subtype_code=SUBTYPES["SEL_SINGLE"], nom_id=1)
    
    f_map["prov_multi"], _ = create_field(campaign_id, sections["Combos"], name="Provincias Interés (Multi-Sel)", 
                                          type_code=TYPES["SELECTOR"], subtype_code=SUBTYPES["SEL_MULTI"], nom_id=2)

    f_map["pais_chk"], _ = create_field(campaign_id, sections["Combos"], name="País (Check)", 
                                        type_code=TYPES["CHECKBOX"], subtype_code=SUBTYPES["CHK_SINGLE"], nom_id=1)
    
    f_map["prov_chk_multi"], _ = create_field(campaign_id, sections["Combos"], name="Zonas (Multi-Chk)", 
                                              type_code=TYPES["CHECKBOX"], subtype_code=SUBTYPES["CHK_MULTI"], nom_id=2)
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
        
        if f_map.get("nombre"): values.append({"field_id": f_map["nombre"], "value": fake.first_name()})
        if f_map.get("apellido"): values.append({"field_id": f_map["apellido"], "value": fake.last_name()})
        if f_map.get("dni"): values.append({"field_id": f_map["dni"], "value": str(fake.unique.random_number(digits=8))})
        if f_map.get("email"): values.append({"field_id": f_map["email"], "value": fake.email()})
        
        if f_map.get("fecha_nac"): values.append({"field_id": f_map["fecha_nac"], "value": fake.date_of_birth().isoformat()})
        if f_map.get("fecha_evento"): values.append({"field_id": f_map["fecha_evento"], "value": fake.future_date().isoformat()})
        if f_map.get("hora_cita"): values.append({"field_id": f_map["hora_cita"], "value": fake.future_datetime().strftime("%Y-%m-%d %H:%M:%S")})
        
        if f_map.get("precio"): values.append({"field_id": f_map["precio"], "value": round(random.uniform(10.5, 999.9), 2)})
        if f_map.get("cantidad"): values.append({"field_id": f_map["cantidad"], "value": random.randint(1, 50)})

        if paises:
            pais_rnd = random.choice(paises)['id']
            if f_map.get("pais_sel"): values.append({"field_id": f_map["pais_sel"], "value": pais_rnd})
            if f_map.get("pais_chk"): values.append({"field_id": f_map["pais_chk"], "value": pais_rnd})

        if provincias:
            provs_rnd = random.sample(provincias, k=random.randint(1, 3))
            provs_ids = [p['id'] for p in provs_rnd]
            if f_map.get("prov_multi"): values.append({"field_id": f_map["prov_multi"], "value": provs_ids})
            if f_map.get("prov_chk_multi"): values.append({"field_id": f_map["prov_chk_multi"], "value": provs_ids})

        if target_leads_ids and f_map.get("referido_por"):
            related = random.sample(target_leads_ids, k=random.randint(1, 2))
            # Ajuste IMPORTANTE: Leads relacionados se envían como LISTA de enteros
            values.append({"field_id": f_map["referido_por"], "value": related})

        create_lead(campaign_id, values)

# --- RUN ---

def run_seed():
    print("\n--- 🚀 SEEDING MASTER V6 (Final) ---")
    
    sections = {
        "Personal": get_lead_field_section("Datos Personales"),
        "Detalles": get_lead_field_section("Detalles"),
        "Combos": get_lead_field_section("Clasificación")
    }
    
    nom_data = {
        'paises': get_nomenclator_items(1),
        'provincias': get_nomenclator_items(2)
    }

    if not nom_data['paises']: print("⚠️ Advertencia: Nomenclador 1 (Países) vacío.")

    ws_id = create_workspace(f"Demo Suite {datetime.now().strftime('%H:%M:%S')}")
    if not ws_id: return

    log(f"Workspace creado: ID {ws_id}")

    # 1. BASE
    camp_base_id = create_campaign("1. Base Clientes", ws_id)
    if camp_base_id:
        map_base = setup_base_campaign(camp_base_id, sections)
        generate_data(camp_base_id, map_base, random.randint(20, 50), nom_data)
        log("Campaña Base generada")
    
    # Recuperamos IDs con seguridad (paginación corregida)
    base_leads_ids = get_leads_ids(camp_base_id) if camp_base_id else []

    # 2. COMPLEJA
    camp_complex_id = create_campaign("2. Tipos Avanzados", ws_id)
    if camp_complex_id:
        map_complex = setup_complex_campaign(camp_complex_id, sections)
        generate_data(camp_complex_id, map_complex, random.randint(20, 50), nom_data)
        log("Campaña Compleja generada")

    # 3. CALCULOS
    camp_calc_id = create_campaign("3. Facturación (Calc)", ws_id)
    if camp_calc_id:
        map_calc = setup_calculated_campaign(camp_calc_id, sections)
        generate_data(camp_calc_id, map_calc, random.randint(20, 50), nom_data)
        log("Campaña Calculada generada")

    # 4. RELACIONES
    if base_leads_ids:
        camp_rel_id = create_campaign("4. Ventas (Relacional)", ws_id)
        if camp_rel_id:
            map_rel = setup_relational_campaign(camp_rel_id, camp_base_id, sections)
            generate_data(camp_rel_id, map_rel, random.randint(20, 50), nom_data, target_leads_ids=base_leads_ids)
            log("Campaña Relacional generada")
    else:
        log("Saltando Campaña Relacional (faltan leads base)", False)

    print("\n--- ✅ SEED COMPLETADO ---")

if __name__ == "__main__":
    run_seed()