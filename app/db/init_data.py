import requests
import re
from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.lead_field import LeadField
from app.models.lead_field_type import LeadFieldType
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.security_models import Permission, Role, User
from app.models.workspace import Workspace

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
        {"code": "FILE", "description": "Archivo"},
    ]
    seed_generic(db, model=LeadFieldType, items=datos, unique_by=["code"])


# -----------------------------------------------------------------------------
# 2. SEED RBAC (Corregido con validaciones)
# -----------------------------------------------------------------------------
def seed_rbac(db):
    print("🔹 Procesando RBAC Automático...")

    ENTITIES = [
        "lead",
        "lead_field",
        "lead_field_type",
        "validation_rule",
        "campaign",
        "nomenclator",
        "nomenclator_item",
        "user",
        "role",
        "permission",
        "workspace"
    ]

    # 2. Definimos las acciones estándar
    ACTIONS = {
        "create": "Crear",
        "view": "Ver",
        "update": "Editar",
        "delete": "Eliminar"
    }

    # Helper get_or_create
    def _get_or_create_permission(codename, name):
        perm = db.query(Permission).filter_by(codename=codename).first()
        if not perm:
            perm = Permission(name=name, codename=codename)
            db.add(perm)
            # No hacemos flush por cada uno para ir rápido, haremos commit al final
        return perm

    # --- Generación Masiva de Permisos ---
    all_permissions = []
    
    for entity in ENTITIES:
        # CRUD Básico: lead:create, lead:view, etc.
        for action_code, action_label in ACTIONS.items():
            codename = f"{entity}:{action_code}"
            name = f"{action_label} {entity.capitalize()}"
            
            p = _get_or_create_permission(codename, name)
            all_permissions.append(p)
        
        # Especial: view_all (para scopes como Leads)
        # Lo creamos para todas por consistencia, o podrías filtrar solo 'lead'
        p_all = _get_or_create_permission(
            f"{entity}:view_all", 
            f"Ver TODOS los {entity.capitalize()}"
        )
        all_permissions.append(p_all)

    db.flush() # Guardamos los permisos para tener IDs

    # --- Roles ---
    def _get_or_create_role(name, code):
        role = db.query(Role).filter_by(code=code).first()
        if not role:
            role = Role(name=name, code=code)
            db.add(role)
            db.flush()
        return role

    r_admin = _get_or_create_role("Admin", "admin")
    r_agent = _get_or_create_role("Vendedor", "agent")

    # --- Asignación de Permisos ---
    
    # 1. Admin: Tiene TODO
    all_db_perms = db.query(Permission).all()
    r_admin.permissions = all_db_perms

    # 2. Vendedor: Lógica específica (Solo Leads operativamente)
    # Filtramos permisos que empiecen con 'lead:' pero NO 'delete' ni 'view_all'
    agent_perms = [
        p for p in all_db_perms 
        if p.codename.startswith("lead:") 
        and "delete" not in p.codename 
        and "view_all" not in p.codename
        and "field" not in p.codename # Que no toque lead_fields
    ]
    r_agent.permissions = agent_perms

    # --- Usuarios ---
    def _get_or_create_user(email, roles_list):
        user = db.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email)
            # Asignamos la lista de roles
            user.roles = roles_list
            db.add(user)
            db.flush()
        return user

    # Creamos un rol extra para probar la asignación múltiple
    p_delete = next((p for p in all_db_perms if p.codename == "lead:delete"), None)
    r_super = _get_or_create_role("Supervisor", "supervisor")

    if p_delete:
        r_super.permissions = [p_delete]

    # Admin tiene Rol Admin
    _get_or_create_user("admin@crm.com", [r_admin])
    
    # Vendedor tiene Rol Vendedor
    _get_or_create_user("vendedor@crm.com", [r_agent])

    # Ejemplo Multi-Rol: Un "Jefe de Ventas" que es Vendedor + Supervisor
    _get_or_create_user("jefe@crm.com", [r_agent, r_super])
    
    db.commit() # Guardamos todo al final

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








