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
    "SELECTOR": "SELECTOR", "CHECKBOX": "CHECKBOX", "MONEY": "MONEY", 
    "URL": "URL", "PHONE": "PHONE", "RATING": "RATING", 
    "ADDRESS": "ADDRESS", "EMAIL": "EMAIL", "BOOL": "BOOL", 
    "FILE": "FILE", "DATE": "DATE", "DATE_TIME": "DATE_TIME", 
    "NUMBER": "NUMBER", "INT": "INT", "CALCULATED": "CALCULATED", "LEAD": "LEAD"
}

SUBTYPES = {
    "SEL_SINGLE": "SELECTOR_SIMPLE", "SEL_MULTI": "SELECTOR_MULTIPLE",
    "URL_WEB": "WEBSITE", "PHONE_MOB": "MOBILE", "PHONE_LAND": "LANDLINE",
    "RATING_STARS": "STAR_RATING", "ADDR_COORDS": "COORDINATES",
    "FILE_IMAGE": "FILE_IMAGE", "FILE_DOC": "FILE_DOCUMENT"
}

# --- HELPERS API ---
def log(msg, success=True, indent=0):
    symbol = "✅" if success else "❌"
    print(f"{' ' * indent}{symbol} {msg}")

def set_tenant(org_id):
    """Cambia el contexto de la sesión a una nueva organización"""
    session.headers.update({"X-Organization-Id": str(org_id)})
    log(f"Contexto cambiado a Organización ID: {org_id}", indent=2)

def create_organization(name, description=None):
    resp = session.post(f"{BASE_URL}/organizations/", json={"name": name, "description": description})
    if resp.status_code in [200, 201]: return resp.json()['id']
    return None

def create_workspace(name):
    resp = session.post(f"{BASE_URL}/workspaces/", json={"name": name})
    if resp.status_code in [200, 201]: return resp.json()['id']
    return None

def create_campaign(name, workspace_id):
    payload = {"name": name, "workspace_id": workspace_id, "active": True}
    resp = session.post(f"{BASE_URL}/campaigns/", json=payload)
    if resp.status_code in [200, 201]: return resp.json()['id']
    return None

def get_lead_field_section(name):
    resp = session.get(f"{BASE_URL}/lead_field_sections?search={name}")
    if resp.status_code == 200 and resp.json().get('items'):
        return resp.json()['items'][0]['id']
    resp = session.post(f"{BASE_URL}/lead_field_sections/", json={"name": name})
    if resp.status_code in [200, 201]: return resp.json()['id']
    return 1

def get_nomenclator_by_name(name):
    """Busca un nomenclador global por nombre y devuelve sus ítems y su ID real"""
    # Buscamos el nomenclador por nombre
    resp = session.get(f"{BASE_URL}/nomenclators?search={name}")
    
    if resp.status_code == 200:
        data = resp.json()
        items = data.get('items', []) if isinstance(data, dict) else data
        
        if items:
            nom_id = items[0]['id']
            # Ahora que tenemos el ID real, traemos sus opciones
            resp_items = session.get(f"{BASE_URL}/nomenclator_items?nomenclator_id={nom_id}&page_size=500")
            
            if resp_items.status_code == 200:
                options = resp_items.json().get("items", [])
                return options, nom_id
                
    print(f"⚠️ Nomenclador '{name}' no encontrado en el sistema.")
    return [], None

def get_or_create_custom_nomenclator(name, options):
    """Crea un nomenclador específico si no existe (ej: Rubros)"""
    items, nom_id = get_nomenclator_by_name(name)
    if items:
        return items, nom_id
        
    # Si no existe, lo creamos localmente
    resp = session.post(f"{BASE_URL}/nomenclators/", json={"name": name, "is_global": False})
    if resp.status_code in [200, 201]:
        nom_id = resp.json()['id']
        for opt in options:
            session.post(f"{BASE_URL}/nomenclator_items/", json={"nomenclator_id": nom_id, "value": opt, "active": True})
        
        return get_nomenclator_by_name(name)
    return [], None

def create_field(campaign_id, section_id, name=None, type_code=None, subtype_code=None, 
                 template_code=None, required=False, nom_id=None, expression=None):
    payload = {"campaign_id": campaign_id, "lead_field_section_id": section_id, "required": required, "is_primary": False, "is_visible": True}
    if template_code: payload["field_template_code"] = template_code
    else:
        payload["name"], payload["field_type_code"] = name, type_code
        if subtype_code: payload["field_subtype_code"] = subtype_code
        if nom_id: payload["nomenclator_id"] = nom_id
        if expression: payload["calculation_expression"] = expression
            
    resp = session.post(f"{BASE_URL}/lead_fields/", json=payload)
    if resp.status_code in [200, 201]: return resp.json()['id']
    print(f"Error creando field {name or template_code}: {resp.text}")
    return None

def create_lead(campaign_id, values):
    clean_values = [v for v in values if v.get("field_id") is not None]
    resp = session.post(f"{BASE_URL}/leads/", json={"campaign_id": campaign_id, "values": clean_values})
    return resp.status_code in [200, 201]

# --- SETUP CAMPAÑAS ---

def setup_b2c_campaign(camp_id, sections, paises_nom_id):
    f = {}
    f["nombre"] = create_field(camp_id, sections["Per"], template_code="FIRST_NAME", required=True)
    f["apellido"] = create_field(camp_id, sections["Per"], template_code="LAST_NAME", required=True)
    f["email"] = create_field(camp_id, sections["Per"], name="Email", type_code="EMAIL", required=True)
    f["telefono"] = create_field(camp_id, sections["Per"], name="Teléfono", type_code="PHONE", subtype_code="MOBILE")
    
    # Domicilio
    f["calle"] = create_field(camp_id, sections["Dom"], name="Calle", type_code="STRING")
    f["altura"] = create_field(camp_id, sections["Dom"], name="Altura", type_code="INT")
    f["piso_depto"] = create_field(camp_id, sections["Dom"], name="Piso/Depto", type_code="STRING")
    f["pais"] = create_field(camp_id, sections["Dom"], name="País", type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=paises_nom_id if paises_nom_id else None)
    
    # Booleanos
    f["acepta_tyc"] = create_field(camp_id, sections["Extra"], name="Acepta TyC", type_code="BOOL", required=True)
    f["newsletter"] = create_field(camp_id, sections["Extra"], name="Suscrito a Ofertas", type_code="BOOL")
    return f

def setup_health_campaign(camp_id, sections):
    f = {}
    f["nombres_apellidos"] = create_field(camp_id, sections["Per"], name="Nombre Completo", type_code="STRING", required=True)
    f["fecha_nac"] = create_field(camp_id, sections["Per"], template_code="BIRTH_DATE")
    
    # Datos Médicos
    f["peso"] = create_field(camp_id, sections["Med"], name="Peso (kg)", type_code="NUMBER")
    f["altura"] = create_field(camp_id, sections["Med"], name="Altura (m)", type_code="NUMBER")
    
    # Calculados con IF
    f["imc"] = create_field(camp_id, sections["Med"], name="IMC", type_code="CALCULATED", expression="ROUND({Peso (kg)} / ({Altura (m)} * {Altura (m)}), 2)")
    f["estado"] = create_field(camp_id, sections["Med"], name="Alerta Médica", type_code="CALCULATED", expression='IF(IMC > 25, "Sobrepeso", IF(IMC < 18.5, "Bajo Peso", "Normal"))')
    return f

def setup_b2b_campaign(camp_id, sections, nom_rubros, paises_nom_id):
    f = {}
    f["nombre"] = create_field(camp_id, sections["B2B"], name="Nombre", type_code="STRING", required=True)
    f["email"] = create_field(camp_id, sections["Per"], name="Email", type_code="EMAIL", required=True)
    f["telefono"] = create_field(camp_id, sections["Per"], name="Teléfono", type_code="PHONE", subtype_code="MOBILE")
    f["razon_social"] = create_field(camp_id, sections["B2B"], name="Razón Social", type_code="STRING", required=True)
    f["cuit"] = create_field(camp_id, sections["B2B"], name="CUIT", type_code="STRING", required=True)
    f["rubro"] = create_field(camp_id, sections["B2B"], name="Rubro", type_code="SELECTOR", subtype_code="SELECTOR_MULTIPLE", nom_id=nom_rubros)
    
    f["calle"] = create_field(camp_id, sections["Dom"], name="Calle", type_code="STRING")
    f["altura"] = create_field(camp_id, sections["Dom"], name="Altura", type_code="INT")
    f["piso_depto"] = create_field(camp_id, sections["Dom"], name="Piso/Depto", type_code="STRING")
    f["pais"] = create_field(camp_id, sections["Dom"], name="País", type_code="SELECTOR", subtype_code="SELECTOR_SIMPLE", nom_id=paises_nom_id if paises_nom_id else None)

    f["website"] = create_field(camp_id, sections["B2B"], name="WebSite", type_code="URL", subtype_code="WEBSITE")
    f["reunion"] = create_field(camp_id, sections["Extra"], name="Próxima Reunión", type_code="DATE_TIME")
    f["constancia"] = create_field(camp_id, sections["Extra"], name="Constancia AFIP", type_code="FILE", subtype_code="FILE_DOCUMENT")
    return f

# --- DATA GEN ---

def generate_leads(camp_id, f, count, type="B2C", nom_data=None):
    log(f"Generando {count} leads para campaña {type}...", indent=4)
    for _ in range(count):
        v = []
        
        # IMPERFECCIÓN: 20% de chances de dejar los campos opcionales vacíos
        is_perfect = random.random() > 0.2 

        if type == "B2C":
            if f.get("nombre"): v.append({"field_id": f["nombre"], "value": fake.first_name()})
            if f.get("apellido"): v.append({"field_id": f["apellido"], "value": fake.last_name()})
            if f.get("email"): v.append({"field_id": f["email"], "value": fake.email()})
            if f.get("telefono") and is_perfect: v.append({"field_id": f["telefono"], "value": f"+549{fake.msisdn()[3:]}"})
            
            if f.get("calle"): v.append({"field_id": f["calle"], "value": fake.street_name()})
            if f.get("altura"): v.append({"field_id": f["altura"], "value": random.randint(100, 9999)})
            # Solo algunos tienen piso/depto
            if f.get("piso_depto") and random.random() > 0.6: v.append({"field_id": f["piso_depto"], "value": f"{random.randint(1,10)}{random.choice(['A','B','C'])}"})
            
            v.append({"field_id": f["acepta_tyc"], "value": True}) # Obligatorio
            v.append({"field_id": f["newsletter"], "value": random.choice([True, False])})

        elif type == "HEALTH":
            if f.get("nombres_apellidos"): v.append({"field_id": f["nombres_apellidos"], "value": fake.name()})
            if f.get("fecha_nac"): v.append({"field_id": f["fecha_nac"], "value": fake.date_of_birth(minimum_age=18, maximum_age=80).isoformat()})
            
            # Generar pesos y alturas realistas
            altura = random.uniform(1.50, 1.95)
            peso = random.uniform(50.0, 110.0)
            if f.get("altura"): v.append({"field_id": f["altura"], "value": round(altura, 2)})
            if f.get("peso"): v.append({"field_id": f["peso"], "value": round(peso, 1)})

        elif type == "B2B":
            if f.get("nombre"): v.append({"field_id": f["nombre"], "value": fake.name()})
            if f.get("email"): v.append({"field_id": f["email"], "value": fake.company_email()})
            if f.get("telefono") and is_perfect: v.append({"field_id": f["telefono"], "value": f"+549{fake.msisdn()[3:]}"})
            if f.get("calle"): v.append({"field_id": f["calle"], "value": fake.street_name()})
            if f.get("altura"): v.append({"field_id": f["altura"], "value": random.randint(100, 9999)})
            if f.get("piso_depto") and random.random() > 0.6: v.append({"field_id": f["piso_depto"], "value": f"{random.randint(1,10)}{random.choice(['A','B','C'])}"})
            if f.get("pais") and nom_data: v.append({"field_id": f["pais"], "value": random.choice(nom_data)['id']})
            
            if f.get("razon_social"): v.append({"field_id": f["razon_social"], "value": f"{fake.company()} {fake.company_suffix()}"})
            if f.get("cuit"): v.append({"field_id": f["cuit"], "value": f"30-{fake.unique.random_number(digits=8)}-9"})
            if f.get("rubro") and nom_data: v.append({"field_id": f["rubro"], "value": random.choice(nom_data)['id']})
            
            if f.get("website") and is_perfect: v.append({"field_id": f["website"], "value": fake.url()})
            
            # Reuniones a futuro
            if f.get("reunion") and is_perfect: 
                future_date = datetime.now() + timedelta(days=random.randint(1, 30), hours=random.randint(9, 17))
                v.append({"field_id": f["reunion"], "value": future_date.strftime("%Y-%m-%d %H:%M:%S")})
                
            if f.get("constancia") and is_perfect:
                v.append({"field_id": f["constancia"], "value": "https://www.afip.gob.ar/constancia/dummy.pdf"})

        create_lead(camp_id, v)

# --- RUN ---

def run_seed():
    print("\n--- 🚀 SEEDING MASTER V8 (Multi-Tenant & Realismo) ---")
    
    # =================================================================
    # ORGANIZACIÓN 1: "MegaCorp B2C"
    # =================================================================
    org1_id = create_organization("MegaCorp S.A.")
    set_tenant(org1_id)
    
    sections_org1 = {
        "Per": get_lead_field_section("Personales"),
        "Dom": get_lead_field_section("Domicilio"),
        "Med": get_lead_field_section("Salud y Métricas"),
        "Extra": get_lead_field_section("Adicionales")
    }
    
    # Nomenclador Dinámico
    paises_items, paises_nom_id = get_nomenclator_by_name("Países")
    
    ws1_id = create_workspace("Consumidores")
    
    # Campaña B2C Normal
    camp_b2c = create_campaign("1. Leads E-Commerce", ws1_id)
    map_b2c = setup_b2c_campaign(camp_b2c, sections_org1, paises_nom_id)
    generate_leads(camp_b2c, map_b2c, 80, "B2C", paises_items)
    
    # Campaña Salud (Fórmulas IF)
    camp_health = create_campaign("2. Pacientes Clínica", ws1_id)
    map_health = setup_health_campaign(camp_health, sections_org1)
    generate_leads(camp_health, map_health, 50, "HEALTH")

    # =================================================================
    # ORGANIZACIÓN 2: "InnovaTech B2B" (Totalmente aislada)
    # =================================================================
    org2_id = create_organization("InnovaTech Solutions")
    set_tenant(org2_id) # CAMBIO DE CONTEXTO MAGICO
    
    sections_org2 = {
        "Per": get_lead_field_section("Contacto"),       
        "Dom": get_lead_field_section("Domicilio"),       
        "B2B": get_lead_field_section("Datos Corporativos"),
        "Extra": get_lead_field_section("Documentación")
    }
    
    rubros_items, nom_rubros = get_or_create_custom_nomenclator("Rubros Empresariales", ["Tecnología", "Agro", "Fintech", "Logística", "Retail"])
    
    ws2_id = create_workspace("Ventas B2B")
    
    # Campaña B2B Empresas
    camp_b2b = create_campaign("1. Prospección Empresas", ws2_id)
    map_b2b = setup_b2b_campaign(camp_b2b, sections_org2, nom_rubros, paises_nom_id)
    generate_leads(camp_b2b, map_b2b, 60, "B2B", rubros_items)

    print("\n--- ✅ SEED COMPLETADO EXITOSAMENTE ---")

if __name__ == "__main__":
    run_seed()