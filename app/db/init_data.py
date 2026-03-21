import requests
import re
from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.lead_field import LeadField
from app.models.lead_field_type import LeadFieldType
from app.models.lead_flow import LeadFlow
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.security_models import Permission, Role, User
from app.models.workspace import Workspace
from app.models.lead_field_subtype import LeadFieldSubtype
from app.models.lead_field_section import LeadFieldSection
from app.models.organization import Organization

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
def run_seeds(db=None):

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        print("🌱 Iniciando Seeders...")
        
        # 1. RBAC (Usuarios, Roles, Permisos)
        seed_rbac(db)
        db.commit() # Commit por bloques para asegurar integridad

        # 2. Tipos de Campos
        seed_lead_field_types(db)
        db.commit()

        seed_lead_field_subtypes(db)
        db.commit()

        seed_lead_field_sections(db)
        db.commit()

        # 3. Geografía
        seed_geography_separated(db)
        db.commit()

        seed_nomenclator_sex(db)
        db.commit()

        seed_test_tenants(db)
        db.commit()

        print("🚀 Seeders finalizados correctamente.")

    except Exception as e:
        print(f"🔥 Error crítico en Seeders: {e}")
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()


def seed_lead_field_sections(db):
    print("Procesando Secciones de Campos...")
    datos = [
        {"name": "Datos Personales"},       
        {"name": "Información de Contacto"},
        {"name": "Detalles Adicionales"}          
    ]
    # Usamos 'name' como clave única para no duplicar
    seed_generic(db, model=LeadFieldSection, items=datos, unique_by=["name"])

# -----------------------------------------------------------------------------
# 1. SEED LEAD FIELD TYPES
# -----------------------------------------------------------------------------
def seed_lead_field_types(db):
    print("Procesando LeadFieldTypes...")
    datos = [
        {"code": "STRING", "description": "Texto"},
        {"code": "INT", "description": "Número entero"},
        {"code": "NUMBER", "description": "Número decimal"},
        {"code": "DATE", "description": "Fecha"},
        {"code": "DATE_TIME", "description": "Fecha y hora"},
        {"code": "BOOL", "description": "Valor verdadero/falso"},
        {"code": "SELECTOR", "description": "Selector"},
        {"code": "CHECKBOX", "description": "Casilla de verificación"},
        {"code": "FILE", "description": "Archivo"},
        {"code": "CALCULATED", "description": "Campo calculado"},
        {"code": "LEAD", "description": "Lead"},
        {"code": "MONEY", "description": "Moneda"},
        {"code": "EMAIL", "description": "Email"},
        {"code": "URL", "description": "Enlace"},
        {"code": "PHONE", "description": "Teléfono"},
        {"code": "RATING", "description": "Rating"},
        {"code": "ADDRESS", "description": "Dirección"},
        {"code": "RICH_TEXT", "description": "Texto Enriquecido"},
        {"code": "TAGS", "description": "Etiquetas"},
        {"code": "PASSWORD", "description": "Contraseña"},
    ]
    seed_generic(db, model=LeadFieldType, items=datos, unique_by=["code"])

def seed_lead_field_subtypes(db):
    print("Procesando LeadFieldSubTypes...")
    datos = [
        {"code": "SELECTOR_MULTIPLE", "description": "Multiple", "lead_field_type_code": "SELECTOR"},
        {"code": "SELECTOR_SIMPLE", "description": "Simple", "lead_field_type_code": "SELECTOR"},
        {"code": "CHECKBOX_MULTIPLE", "description": "Multiple", "lead_field_type_code": "CHECKBOX"},
        {"code": "CHECKBOX_SIMPLE", "description": "Simple", "lead_field_type_code": "CHECKBOX"},
        {"code": "FILE_IMAGE", "description": "Imagen", "lead_field_type_code": "FILE"},
        {"code": "FILE_DOCUMENT", "description": "Documento", "lead_field_type_code": "FILE"},
        {"code": "WEBSITE", "description": "Sitio Web", "lead_field_type_code": "URL"},
        {"code": "SOCIAL_MEDIA", "description": "Red Social", "lead_field_type_code": "URL"},
        {"code": "WHATSAPP", "description": "WhatsApp", "lead_field_type_code": "PHONE"},
        {"code": "MOBILE", "description": "Teléfono Movil", "lead_field_type_code": "PHONE"},
        {"code": "LANDLINE", "description": "Teléfono Fijo", "lead_field_type_code": "PHONE"},
        {"code": "STAR_RATING", "description": "Calificación de estrellas", "lead_field_type_code": "RATING"},
        {"code": "NPS", "description": "Indicador del 1 al 10", "lead_field_type_code": "RATING"},
        {"code": "SCORE", "description": "Valor del 0 al 100", "lead_field_type_code": "RATING"},
        {"code": "SIMPLE_ADDRESS", "description": "Texto Plano multi-línea", "lead_field_type_code": "ADDRESS"},
        {"code": "MAPS_URL", "description": "URL de Google Maps", "lead_field_type_code": "ADDRESS"},
        {"code": "COORDINATES", "description": "Latitud y Longitud", "lead_field_type_code": "ADDRESS"},
        {"code": "HTML", "description": "HTML", "lead_field_type_code": "RICH_TEXT"},
        {"code": "MARKDOWN", "description": "MARKDOWN", "lead_field_type_code": "RICH_TEXT"},
    ]
    seed_generic(db, model=LeadFieldSubtype, items=datos, unique_by=["code"],resolve_fk={"lead_field_type_code": (LeadFieldType, "code")}
    )
# -----------------------------------------------------------------------------
# 2. SEED RBAC (Corregido con validaciones)
# -----------------------------------------------------------------------------
def seed_rbac(db):
    print("Procesando RBAC Automático...")

    # 1. Entidades con CRUD Completo
    FULL_CRUD_ENTITIES = [
        "lead", "lead_field", "validation_rule",
        "campaign", "nomenclator", "nomenclator_item", "user",
        "role", "workspace", "lead_field_section",
        "lead_comment", "organization", "lead_flow", "lead_state", 
        "lead_state_transition", "team", "team_member", 
        "team_workspace_access", "team_campaign_access", "lead_routing_rule"
    ]

    # 2. Entidades de Solo Lectura (Catálogos del sistema)
    READ_ONLY_ENTITIES = [
        "lead_field_type", 
        "lead_field_subtype",
        "permission", "lead_state_history", "system_audit_log", "lead_activity_history"
    ]

    ACTIONS = {
        "create": "Crear", 
        "view": "Ver", 
        "update": "Editar", 
        "delete": "Eliminar"
    }

    def _get_or_create_permission(codename, name):
        perm = db.query(Permission).filter_by(codename=codename).first()
        if not perm:
            perm = Permission(name=name, codename=codename)
            db.add(perm)
        return perm

    # --- 1. Generación Masiva de Permisos ---
    all_permissions = []
    
    # Procesar entidades con CRUD completo
    for entity in FULL_CRUD_ENTITIES:
        # Formateamos el nombre visual (ej: "lead_field" -> "Lead Field")
        entity_name_visual = entity.replace('_', ' ').title()

        for action_code, action_label in ACTIONS.items():
            codename = f"{entity}:{action_code}"
            name = f"{action_label} {entity_name_visual}"
            p = _get_or_create_permission(codename, name)
            all_permissions.append(p)
        
        p_all = _get_or_create_permission(f"{entity}:view_all", f"Ver TODOS los {entity_name_visual}")
        all_permissions.append(p_all)

    # Procesar entidades de Solo Lectura
    for entity in READ_ONLY_ENTITIES:
        entity_name_visual = entity.replace('_', ' ').title()

        # Solo permiso para ver uno específico
        p_view = _get_or_create_permission(f"{entity}:view", f"Ver {entity_name_visual}")
        all_permissions.append(p_view)
        
        # Solo permiso para ver todos (listados)
        p_all = _get_or_create_permission(f"{entity}:view_all", f"Ver TODOS los {entity_name_visual}")
        all_permissions.append(p_all)

    db.flush()

    # --- 2. Roles del Sistema (Plantillas globales) ---
    def _get_or_create_system_role(name, code):
        # organization_id=None significa que es un rol global/plantilla
        role = db.query(Role).filter_by(code=code, organization_id=None).first()
        if not role:
            role = Role(name=name, code=code, organization_id=None)
            db.add(role)
            db.flush()
        return role

    r_admin = _get_or_create_system_role("Admin Global", "admin")

    # Asignamos TODOS los permisos (incluyendo los de solo lectura) al rol Admin Global
    all_db_perms = db.query(Permission).all()
    r_admin.permissions = all_db_perms

    # --- 3. Usuario SuperAdmin (Sin Organización) ---
    def _get_or_create_superadmin(email):
        user = db.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email, is_superuser=True) 
            db.add(user)
            db.flush()
        return user

    # Creamos al admin. Al ser is_superuser=True, no necesita estar 
    # en la tabla UserOrganization para tener permisos totales.
    _get_or_create_superadmin("admin@crm.com")
    
    db.commit()

def seed_test_tenants(db):
    print("🏢 Iniciando Seed de Organizaciones de Prueba (Multi-Tenant)...")

    # 1. Crear Organizaciones
    org_alpha = db.query(Organization).filter_by(name="Empresa Alpha").first()
    if not org_alpha:
        org_alpha = Organization(name="Empresa Alpha", description="Tenant A para pruebas")
        db.add(org_alpha)
    
    org_beta = db.query(Organization).filter_by(name="Empresa Beta").first()
    if not org_beta:
        org_beta = Organization(name="Empresa Beta", description="Tenant B para pruebas")
        db.add(org_beta)

    db.flush() # Flush para que la DB les asigne los IDs

    # 2. Obtener el rol global de Admin (creado previamente por seed_rbac)
    role_base = db.query(Role).filter_by(code="admin", organization_id=None).first()
    if not role_base:
        print("⚠️ Advertencia: No se encontró el rol 'admin'. Asegúrate de ejecutar seed_rbac primero.")
        return

    # 3. Helper interno para crear al usuario y sus membresías
    def _create_test_user(email, memberships_info):
        """
        memberships_info es una lista de tuplas: [(org_obj, role_obj), ...]
        """
        user = db.query(User).filter_by(email=email).first()
        if not user:
            # IMPORTANTE: is_superuser=False para que la seguridad actúe sobre ellos
            user = User(email=email, is_superuser=False)
            db.add(user)
            db.flush()

        for org_obj, role_obj in memberships_info:
            from app.models.security_models import UserOrganization
            
            membership = db.query(UserOrganization).filter_by(
                user_id=user.id, 
                organization_id=org_obj.id
            ).first()
            
            if not membership:
                membership = UserOrganization(
                    user_id=user.id,
                    organization_id=org_obj.id,
                    active=True
                )
                # Asignamos el rol a esta membresía específica
                membership.roles = [role_obj]
                db.add(membership)
        
        db.flush()
        return user

    # 4. Crear los Usuarios de Prueba
    
    # A. Usuario de una sola empresa (Alpha)
    _create_test_user("user_alpha@test.com", [(org_alpha, role_base)])
    
    # B. Usuario de una sola empresa (Beta)
    _create_test_user("user_beta@test.com", [(org_beta, role_base)])
    
    # C. Usuario Multi-Empresa (Alpha y Beta)
    user_multi = _create_test_user("user_multi@test.com", [
        (org_alpha, role_base), 
        (org_beta, role_base)
    ])

    print("✅ Organizaciones y Usuarios de prueba creados con éxito.")


def get_or_create_nomenclator(db, name):
        nom = db.query(Nomenclator).filter_by(name=name).first()
        if not nom:
            nom = Nomenclator(name=name)
            db.add(nom)
            db.flush()
        return nom

def get_or_create_nomenclator_item(db, nomenclator_id, code, value, parent_id):
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

# -----------------------------------------------------------------------------
# 3. SEED GEOGRAFÍA
# -----------------------------------------------------------------------------
def seed_geography_separated(db):
    print("🌍 Iniciando Seed de Geografía...")

    # 1. Nomencladores Base
    nom_pais = get_or_create_nomenclator(db, "Países")
    nom_prov = get_or_create_nomenclator(db, "Provincias")

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
            country_item = get_or_create_nomenclator_item(
                db=db,
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

                get_or_create_nomenclator_item(
                    db=db,
                    nomenclator_id=nom_prov.id,
                    code=s_full_code,
                    value=s_name,
                    parent_id=country_item.id 
                )

    except Exception as e:
        print(f"⚠️ Error procesando geografía (puede ser conexión): {e}")
        # No hacemos rollback aquí para no matar los seeds anteriores, solo geografía fallará


def seed_nomenclator_sex(db):
    print("Procesando Nomenclador 'Sexo'...")
    datos = [
        {"code": "MALE", "value": "Masculino"},
        {"code": "FEMALE", "value": "Femenino"},
        {"code": "OTHER", "value": "Otro"},
    ]

    nom_gen = get_or_create_nomenclator(db, "Genero")

    for item in datos:
        get_or_create_nomenclator_item(
            db=db,
            nomenclator_id=nom_gen.id, 
            code=item["code"],
            value=item["value"],
            parent_id=None
        )





