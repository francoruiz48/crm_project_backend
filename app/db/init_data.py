import requests
import re
from app.db.session import SessionLocal
from app.models.lead_field_type import LeadFieldType
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem

def seed_generic(
    db,
    model,
    items: list[dict],
    unique_by: list[str],
    resolve_fk: dict[str, tuple] = None,
):
    """
    model: Modelo SQLAlchemy destino
    items: lista de diccionarios con datos
    unique_by: campos que identifican un registro existente
    resolve_fk: { "campo_fk": (ModeloFK, "campo_lookup") }
    """

    resolve_fk = resolve_fk or {}

    for item in items:
        data = item.copy()

        # 1. Resolver foreign keys
        for fk_field, (fk_model, lookup_field) in resolve_fk.items():
            lookup_value = item.get(fk_field)

            if lookup_value is None:
                continue

            fk_obj = db.query(fk_model).filter(
                getattr(fk_model, lookup_field) == lookup_value
            ).first()

            if not fk_obj:
                raise ValueError(
                    f"[Seeder] No existe {fk_model.__name__}.{lookup_field} = {lookup_value}"
                )

            data[fk_field] = lookup_value

        # 2. Verificar existencia por clave única múltiple
        filters = {field: data[field] for field in unique_by}

        exists = db.query(model).filter_by(**filters).first()
        if exists:
            continue

        # 3. Insertar
        db.add(model(**data))



def run_seeds():
    db = SessionLocal()
    try:
        seed_lead_field_types(db)
        db.commit()
        seed_geography_separated(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_lead_field_types(db):
    datos = [
        {"code": "STRING", "description": "Texto"},
        {"code": "INT", "description": "Número entero"},
        {"code": "NUMBER", "description": "Número decimal"},
        {"code": "DATE", "description": "Fecha"},
        {"code": "BOOL", "description": "Valor verdadero/falso"},
    ]

    seed_generic(db, model = LeadFieldType, items = datos, unique_by=["code"])


def seed_geography_separated(db):
    """
    Crea 3 Nomencladores independientes: 'Países', 'Provincias' y 'Ciudades'.
    Los items de Provincias tienen como padre a items de Países.
    """
    print("🌍 Iniciando Seed de Geografía (Estructura Separada)...")

    # --- PASO 1: Crear los 3 Nomencladores ---
    # Usamos un diccionario para guardar los objetos y sus IDs
    noms = {
        "PAIS": _get_or_create_nomenclator(db, "Países"),
        "PROV": _get_or_create_nomenclator(db, "Provincias"),
        "CIUD": _get_or_create_nomenclator(db, "Ciudades")
    }
    
    # --- CONFIGURACIÓN API ---
    TARGET_COUNTRIES = ["AR", "CL", "BR", "ES", "US"] 
    API_BASE = "https://countriesnow.space/api/v0.1/countries"
    
    try:
        # Traemos Países + Estados
        resp = requests.get(f"{API_BASE}/states")
        data = resp.json()
        
        if data.get("error"):
            print("❌ Error en API externa")
            return

        all_countries = data.get("data", [])
        selected = [c for c in all_countries if c['iso2'] in TARGET_COUNTRIES]

        for country in selected:
            c_name = country['name']
            c_iso = country['iso2']
            c_states = country['states']

            print(f"   📍 Procesando: {c_name}...")

            # --- PASO 2: Crear Item en Nomenclador PAÍSES ---
            # Este item no tiene padre (parent_id=None)
            country_item = _get_or_create_item(
                db, 
                nomenclator_id=noms["PAIS"].id, 
                code=c_iso, 
                value=c_name, 
                parent_id=None 
            )

            # --- PASO 3: Crear Items en Nomenclador PROVINCIAS ---
            for state in c_states:
                s_name = state['name']
                # Código único: AR-Mendoza
                s_code_suffix = state.get('state_code') or re.sub(r'[^a-zA-Z0-9]', '', s_name)[:3].upper()
                s_full_code = f"{c_iso}-{s_code_suffix}"

                # AQUÍ ESTÁ LA CLAVE: 
                # El nomenclator_id es PROVINCIAS, pero el parent_id es del PAÍS
                state_item = _get_or_create_item(
                    db,
                    nomenclator_id=noms["PROV"].id,
                    code=s_full_code,
                    value=s_name,
                    parent_id=country_item.id 
                )

                # --- PASO 4 (Opcional): Ciudades ---
                # Si descomentas esto, recuerda que tardará mucho por las peticiones HTTP
                # _seed_cities_for_state_separated(db, noms["CIUD"].id, country_item.value, state_item)

            db.commit() 

    except Exception as e:
        print(f"🔥 Error procesando geografía: {e}")
        db.rollback()

# --- HELPERS ---

def _get_or_create_nomenclator(db, name):
    nom = db.query(Nomenclator).filter_by(name=name).first()
    if not nom:
        nom = Nomenclator(name=name)
        db.add(nom)
        db.commit() # Commit inmediato para tener ID
        db.refresh(nom)
    return nom

def _get_or_create_item(db, nomenclator_id, code, value, parent_id):
    """Busca por código dentro del mismo nomenclador"""
    item = db.query(NomenclatorItem).filter_by(code=code, nomenclator_id=nomenclator_id).first()
    
    if not item:
        item = NomenclatorItem(
            code=code,
            value=value,
            nomenclator_id=nomenclator_id,
            parent_item_id=parent_id # Aquí vinculamos con el padre (que puede ser de otro nomenclador)
        )
        db.add(item)
        db.flush() # Flush para obtener el ID sin cerrar la transacción
        
    return item

def _seed_cities_for_state_separated(db, cities_nomenclator_id, country_name, state_item):
    """Lógica para cargar ciudades en el nomenclador de Ciudades"""
    url = "https://countriesnow.space/api/v0.1/countries/state/cities"
    payload = { "country": country_name, "state": state_item.value }
    
    try:
        resp = requests.post(url, json=payload)
        res_json = resp.json()
        if not res_json.get("error"):
            cities = res_json.get("data", [])
            for city_name in cities[:20]: # Limitado a 20 para pruebas
                clean_city = re.sub(r'[^a-zA-Z0-9]', '', city_name)
                # Código: AR-M-GodoyCruz
                city_code = f"{state_item.code}-{clean_city}"[:50]

                _get_or_create_item(
                    db,
                    nomenclator_id=cities_nomenclator_id, # ID del nomenclador CIUDADES
                    code=city_code,
                    value=city_name,
                    parent_id=state_item.id # ID del item PROVINCIA
                )
    except Exception:
        pass