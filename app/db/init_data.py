import requests
import re
from app.db.session import SessionLocal
from app.models.lead_field_type import LeadFieldType
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.security_models import Permission, Role, User

# -----------------------------------------------------------------------------
# HELPER GENÉRICO
# -----------------------------------------------------------------------------
def seed_generic(
    db,
    model,
    items: list[dict],
    unique_by: list[str],
    resolve_fk: dict[str, tuple] = None,
):
    """
    Inserta datos solo si no existen previamente.
    """
    resolve_fk = resolve_fk or {}
    created_count = 0

    for item in items:
        data = item.copy()

        # 1. Resolver foreign keys
        should_skip = False
        for fk_field, (fk_model, lookup_field) in resolve_fk.items():
            lookup_value = item.get(fk_field)
            if lookup_value is None:
                continue

            fk_obj = db.query(fk_model).filter(
                getattr(fk_model, lookup_field) == lookup_value
            ).first()

            if not fk_obj:
                print(f"⚠️ [Seeder] Saltando registro. No existe {fk_model.__name__}.{lookup_field} = {lookup_value}")
                should_skip = True
                break

            data[fk_field] = lookup_value
        
        if should_skip:
            continue

        # 2. Verificar existencia por clave única múltiple
        filters = {field: data[field] for field in unique_by if field in data}
        
        # Si filters está vacío, es peligroso filtrar, mejor saltar
        if not filters:
            continue

        exists = db.query(model).filter_by(**filters).first()
        if exists:
            # Ya existe, no hacemos nada
            continue

        # 3. Insertar
        db.add(model(**data))
        created_count += 1
    
    if created_count > 0:
        print(f"   ✅ Se crearon {created_count} registros en {model.__name__}")


# -----------------------------------------------------------------------------
# EXECUTOR PRINCIPAL
# -----------------------------------------------------------------------------
def run_seeds():
    db = SessionLocal()
    try:
        print("🌱 Iniciando Seeders...")
        
        # 1. RBAC (Usuarios, Roles, Permisos)
        seed_rbac(db)
        db.commit() # Commit por bloques para asegurar integridad

        # 2. Tipos de Campos
        seed_lead_field_types(db)
        db.commit()

        # 3. Geografía
        seed_geography_separated(db)
        db.commit()
        
        print("🚀 Seeders finalizados correctamente.")

    except Exception as e:
        print(f"🔥 Error crítico en Seeders: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# -----------------------------------------------------------------------------
# 1. SEED LEAD FIELD TYPES
# -----------------------------------------------------------------------------
def seed_lead_field_types(db):
    print("🔹 Procesando LeadFieldTypes...")
    datos = [
        {"code": "STRING", "description": "Texto"},
        {"code": "INT", "description": "Número entero"},
        {"code": "NUMBER", "description": "Número decimal"},
        {"code": "DATE", "description": "Fecha"},
        {"code": "BOOL", "description": "Valor verdadero/falso"},
    ]
    seed_generic(db, model=LeadFieldType, items=datos, unique_by=["code"])


# -----------------------------------------------------------------------------
# 2. SEED RBAC (Corregido con validaciones)
# -----------------------------------------------------------------------------
def seed_rbac(db):
    print("🔹 Procesando RBAC (Permisos, Roles, Usuarios)...")

    # --- A. Permisos ---
    # Helper local para verificar existencia
    def _get_or_create_permission(name, codename):
        perm = db.query(Permission).filter_by(codename=codename).first()
        if not perm:
            perm = Permission(name=name, codename=codename)
            db.add(perm)
            db.flush() # Flush para tener ID disponible si fuera necesario
        return perm

    p1 = _get_or_create_permission("Crear Lead", "lead:create")
    p2 = _get_or_create_permission("Ver Leads", "lead:view")
    p3 = _get_or_create_permission("Ver TODOS los Leads", "lead:view_all")
    p4 = _get_or_create_permission("Editar Lead", "lead:update")

    # --- B. Roles ---
    def _get_or_create_role(name, code, perms_list):
        role = db.query(Role).filter_by(code=code).first()
        if not role:
            role = Role(name=name, code=code)
            # Asignamos la relación Many-to-Many
            role.permissions = perms_list
            db.add(role)
            db.flush()
        return role

    r_admin = _get_or_create_role("Admin", "admin", [p1, p2, p3, p4])
    r_agent = _get_or_create_role("Vendedor", "agent", [p1, p2]) # Vendedor solo crea y ve lo suyo

    # --- C. Usuarios ---
    def _get_or_create_user(email, role_obj):
        user = db.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email, role_id=role_obj.id)
            db.add(user)
            db.flush()
        return user

    _get_or_create_user("admin@crm.com", r_admin)
    _get_or_create_user("vendedor@crm.com", r_agent)


# -----------------------------------------------------------------------------
# 3. SEED GEOGRAFÍA
# -----------------------------------------------------------------------------
def seed_geography_separated(db):
    print("🌍 Iniciando Seed de Geografía...")

    # Helpers específicos para geografía
    def _get_or_create_nom(name):
        nom = db.query(Nomenclator).filter_by(name=name).first()
        if not nom:
            nom = Nomenclator(name=name)
            db.add(nom)
            db.flush()
        return nom

    def _get_or_create_item(nomenclator_id, code, value, parent_id):
        item = db.query(NomenclatorItem).filter_by(code=code, nomenclator_id=nomenclator_id).first()
        if not item:
            item = NomenclatorItem(
                code=code,
                value=value,
                nomenclator_id=nomenclator_id,
                parent_item_id=parent_id
            )
            db.add(item)
            db.flush()
        return item

    # 1. Nomencladores Base
    nom_pais = _get_or_create_nom("Países")
    nom_prov = _get_or_create_nom("Provincias")
    # nom_ciud = _get_or_create_nom("Ciudades") # Opcional

    # 2. Datos Externos
    TARGET_COUNTRIES = ["AR", "CL", "BR", "ES", "US"] 
    API_BASE = "https://countriesnow.space/api/v0.1/countries"
    
    try:
        # Petición HTTP
        resp = requests.get(f"{API_BASE}/states")
        data = resp.json()
        
        if data.get("error"):
            print("❌ Error en API externa de geografía")
            return

        all_countries = data.get("data", [])
        selected = [c for c in all_countries if c['iso2'] in TARGET_COUNTRIES]

        for country in selected:
            c_name = country['name']
            c_iso = country['iso2']
            c_states = country['states']

            # País
            country_item = _get_or_create_item(
                nomenclator_id=nom_pais.id, 
                code=c_iso, 
                value=c_name, 
                parent_id=None 
            )

            # Provincias / Estados
            for state in c_states:
                s_name = state['name']
                # Generación de código seguro
                s_code_suffix = state.get('state_code') or re.sub(r'[^a-zA-Z0-9]', '', s_name)[:3].upper()
                s_full_code = f"{c_iso}-{s_code_suffix}"

                _get_or_create_item(
                    nomenclator_id=nom_prov.id,
                    code=s_full_code,
                    value=s_name,
                    parent_id=country_item.id 
                )

    except Exception as e:
        print(f"⚠️ Error procesando geografía (puede ser conexión): {e}")
        # No hacemos rollback aquí para no matar los seeds anteriores, solo geografía fallará