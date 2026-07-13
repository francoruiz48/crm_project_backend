import requests
import re
from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.lead_field import LeadField
from app.models.lead_field_type import LeadFieldType
from app.models.lead_flow import LeadFlow
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.models.security_models import Permission, Role, User, UserOrganization
from app.models.workspace import Workspace
from app.models.lead_field_subtype import LeadFieldSubtype
from app.models.lead_field_section import LeadFieldSection
from app.models.organization import Organization
from app.core.dictionaries import SYSTEM_ENTITIES_REGISTRY
from app.core.constans import ADMIN_ORG_ID

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

        # 0. Organización del sistema (debe ser la primera, obtiene id=1)
        seed_admin_org(db)
        db.commit()

        # 1. RBAC (Usuarios, Roles, Permisos)
        seed_rbac(db)
        db.commit() # Commit por bloques para asegurar integridad

        # 2. Tipos de Campos
        seed_lead_field_types(db)
        db.commit()

        seed_lead_field_subtypes(db)
        db.commit()

        # 3. Geografía
        seed_geography_separated(db)
        db.commit()

        seed_nomenclator_sex(db)
        db.commit()

        print("🚀 Seeders finalizados correctamente.")

    except Exception as e:
        print(f"🔥 Error crítico en Seeders: {e}")
        db.rollback()
        raise
    finally:
        if should_close:
            db.close()

# -----------------------------------------------------------------------------
# 0. SEED ORGANIZACIÓN ADMIN DEL SISTEMA
# -----------------------------------------------------------------------------
def seed_admin_org(db):
    """Crea la organización del sistema si no existe. Siempre debe tener id=ADMIN_ORG_ID."""
    print("Procesando Organización del Sistema...")
    org = db.query(Organization).filter_by(id=ADMIN_ORG_ID).first()
    if not org:
        org = Organization(
            name="Panel Global",
            description="Organización interna del sistema.",
        )
        db.add(org)
        db.flush()
        if org.id != ADMIN_ORG_ID:
            raise RuntimeError(
                f"La org admin debería tener id={ADMIN_ORG_ID} pero obtuvo id={org.id}. "
                "Asegurate de que la tabla organization esté vacía antes del primer seed."
            )
        print(f"   ✅ Organización 'Sistema' creada con id={org.id}")
    else:
        print(f"   ℹ️  Organización del sistema ya existe (id={org.id})")
    return org


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
        {"code": "FILE", "description": "Archivo"},
        {"code": "CALCULATED", "description": "Campo calculado"},
        {"code": "LEAD", "description": "Lead"},
    ]
    seed_generic(db, model=LeadFieldType, items=datos, unique_by=["code"])

def seed_lead_field_subtypes(db):
    print("Procesando LeadFieldSubTypes...")
    datos = [
        # SELECTOR
        {"code": "SELECTOR_MULTIPLE", "description": "Selector Múltiple", "lead_field_type_code": "SELECTOR"},
        {"code": "SELECTOR_SIMPLE",   "description": "Selector Simple",   "lead_field_type_code": "SELECTOR"},
        {"code": "CHECKBOX_MULTIPLE", "description": "Checkbox Múltiple", "lead_field_type_code": "SELECTOR"},
        {"code": "CHECKBOX_SIMPLE",   "description": "Checkbox Simple",   "lead_field_type_code": "SELECTOR"},
        # FILE
        {"code": "FILE_IMAGE",    "description": "Imagen",    "lead_field_type_code": "FILE"},
        {"code": "FILE_DOCUMENT", "description": "Documento", "lead_field_type_code": "FILE"},
        # NUMBER
        {"code": "MONEY",       "description": "Valor Monetario",           "lead_field_type_code": "NUMBER"},
        {"code": "PERCENTAGE",  "description": "Porcentaje",                "lead_field_type_code": "NUMBER"},
        {"code": "STAR_RATING", "description": "Calificación de estrellas", "lead_field_type_code": "NUMBER"},
        {"code": "NPS",         "description": "Indicador del 0 al 10",     "lead_field_type_code": "NUMBER"},
        {"code": "SCORE",       "description": "Valor del 0 al 100",        "lead_field_type_code": "NUMBER"},
        # STRING
        {"code": "EMAIL",          "description": "Correo Electrónico",     "lead_field_type_code": "STRING"},
        {"code": "URL",            "description": "Enlace",                 "lead_field_type_code": "STRING"},
        {"code": "WEBSITE",        "description": "Sitio Web",              "lead_field_type_code": "STRING"},
        {"code": "SOCIAL_MEDIA",   "description": "Red Social",             "lead_field_type_code": "STRING"},
        {"code": "WHATSAPP",       "description": "WhatsApp",               "lead_field_type_code": "STRING"},
        {"code": "MOBILE",         "description": "Teléfono Móvil",         "lead_field_type_code": "STRING"},
        {"code": "PHONE",          "description": "Teléfono",               "lead_field_type_code": "STRING"},
        {"code": "LANDLINE",       "description": "Teléfono Fijo",          "lead_field_type_code": "STRING"},
        {"code": "SIMPLE_ADDRESS", "description": "Dirección (texto libre)", "lead_field_type_code": "STRING"},
        {"code": "MAPS_URL",       "description": "URL de Google Maps",     "lead_field_type_code": "STRING"},
        {"code": "COORDINATES",    "description": "Latitud y Longitud",     "lead_field_type_code": "STRING"},
        {"code": "HTML",           "description": "HTML",                   "lead_field_type_code": "STRING"},
        {"code": "MARKDOWN",       "description": "Markdown",               "lead_field_type_code": "STRING"},
        {"code": "PASSWORD",       "description": "Contraseña",             "lead_field_type_code": "STRING"},
        # DATE
        {"code": "DATE_ONLY",   "description": "Solo fecha (sin hora)",  "lead_field_type_code": "DATE"},
        {"code": "BIRTH_DATE",  "description": "Fecha de nacimiento",    "lead_field_type_code": "DATE"},
        # DATE_TIME
        {"code": "TIME_ONLY",   "description": "Solo hora (sin fecha)", "lead_field_type_code": "DATE_TIME"},
        {"code": "DATE_EVENT",  "description": "Fecha de Evento",       "lead_field_type_code": "DATE_TIME"},
    ]
    seed_generic(db, model=LeadFieldSubtype, items=datos, unique_by=["code"],resolve_fk={"lead_field_type_code": (LeadFieldType, "code")}
    )
# -----------------------------------------------------------------------------
# 2. SEED RBAC (Corregido con validaciones)
# -----------------------------------------------------------------------------
def seed_rbac(db):
    print("Procesando RBAC Automático...")

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

    # Iteramos sobre nuestra Única Fuente de Verdad
    for entity_code, entity_info in SYSTEM_ENTITIES_REGISTRY.items():
        entity_name_visual = entity_info["name"]
        crud_type = entity_info["crud_type"]

        if crud_type == "FULL":
            # Genera: Crear, Ver, Editar, Eliminar
            for action_code, action_label in ACTIONS.items():
                codename = f"{entity_code}:{action_code}"
                name = f"{action_label} {entity_name_visual}"
                all_permissions.append(_get_or_create_permission(codename, name))

        elif crud_type == "READ_ONLY":
            # Genera solo: Ver
            codename = f"{entity_code}:view"
            name = f"Ver {entity_name_visual}"
            all_permissions.append(_get_or_create_permission(codename, name))

        # Ambas (FULL y READ_ONLY) siempre tienen el permiso general de "Ver TODOS" (Listar)
        p_all = _get_or_create_permission(f"{entity_code}:view_all", f"Ver TODOS los registros de {entity_name_visual}")
        all_permissions.append(p_all)

    # Permiso especial: invitar usuarios (no forma parte del CRUD estándar)
    _get_or_create_permission("user:invite", "Invitar Usuarios a la Organización")

    db.flush()

    # --- 2. Roles del Sistema (Plantillas en org admin) ---
    admin_org = db.query(Organization).filter_by(id=ADMIN_ORG_ID).first()
    if not admin_org:
        raise RuntimeError(f"No se encontró la organización admin (id={ADMIN_ORG_ID}). Ejecutá seed_admin_org primero.")

    def _get_or_create_system_role(name, code):
        role = db.query(Role).filter_by(code=code, organization_id=ADMIN_ORG_ID).first()
        if not role:
            role = Role(name=name, code=code, organization_id=ADMIN_ORG_ID)
            db.add(role)
            db.flush()
        return role

    # -- Rol Admin: todos los permisos --
    r_admin = _get_or_create_system_role("Administrador", "admin")
    all_db_perms = db.query(Permission).all()
    r_admin.permissions = all_db_perms

    # -- Rol Agent: operaciones del día a día, sin configuración del sistema --
    r_agent = _get_or_create_system_role("Agente", "agent")
    AGENT_PERMS = [
        # Leads
        "lead:view", "lead:create", "lead:update", "lead:delete",
        # Comentarios
        "lead_comment:view", "lead_comment:create", "lead_comment:update", "lead_comment:delete",
        # Vistas propias
        "lead_view:view", "lead_view:view_all", "lead_view:create", "lead_view:update", "lead_view:delete",
        # Etiquetas
        "tag:view", "tag:view_all", "tag:create",
        # Lectura de catálogos
        "campaign:view", "workspace:view",
        "lead_field:view", "lead_field:view_all",
        "lead_field_type:view", "lead_field_type:view_all",
        "lead_field_subtype:view", "lead_field_subtype:view_all",
        "lead_state:view", "lead_state:view_all",
        "lead_state_transition:view", "lead_state_transition:view_all",
        "lead_flow:view", "lead_flow:view_all",
        "nomenclator:view", "nomenclator:view_all",
        "nomenclator_item:view", "nomenclator_item:view_all",
        # Historial
        "lead_state_history:view", "lead_state_history:view_all",
        "lead_activity_history:view", "lead_activity_history:view_all",
        # Equipo (solo lectura)
        "team:view", "team_member:view", "team_member:view_all",
        # Estados de contacto — hallazgo #27 (2026-07-11): agent puede crear/editar,
        # no borrar (decisión del usuario).
        "lead_contact_state:view", "lead_contact_state:view_all",
        "lead_contact_state:create", "lead_contact_state:update",
    ]
    agent_perms = db.query(Permission).filter(Permission.codename.in_(AGENT_PERMS)).all()
    r_agent.permissions = agent_perms

    # -- Rol Viewer: solo lectura --
    r_viewer = _get_or_create_system_role("Visualizador", "viewer")
    VIEWER_PERMS = [
        "lead:view", "lead:view_all",
        "lead_comment:view", "lead_comment:view_all",
        "campaign:view", "workspace:view",
        "lead_field:view", "lead_field:view_all",
        "lead_state:view", "lead_state:view_all",
        "lead_flow:view", "lead_flow:view_all",
        "nomenclator:view", "nomenclator:view_all",
        "nomenclator_item:view", "nomenclator_item:view_all",
        "lead_state_history:view", "lead_state_history:view_all",
        "lead_activity_history:view", "lead_activity_history:view_all",
        "tag:view", "tag:view_all",
        "team:view", "team_member:view",
        # Estados de contacto — hallazgo #27 (2026-07-11): viewer solo lectura.
        "lead_contact_state:view", "lead_contact_state:view_all",
    ]
    viewer_perms = db.query(Permission).filter(Permission.codename.in_(VIEWER_PERMS)).all()
    r_viewer.permissions = viewer_perms

    db.flush()

    # --- 3. Usuarios SuperAdmin + membresía en org admin ---
    def _get_or_create_superadmin(name, last_name, email, password):
        from app.core.security import hash_password
        user = db.query(User).filter_by(email=email).first()
        if not user:
            user = User(
                name=name,
                last_name=last_name,
                email=email,
                is_superuser=True,
                hashed_password=hash_password(password),
            )
            db.add(user)
            db.flush()
        elif not user.hashed_password:
            user.hashed_password = hash_password(password)

        # Vincular superadmin a la org admin como owner (si no existe ya)
        link = db.query(UserOrganization).filter_by(
            user_id=user.id, organization_id=ADMIN_ORG_ID
        ).first()
        if not link:
            link = UserOrganization(
                user_id=user.id,
                organization_id=ADMIN_ORG_ID,
                is_owner=True,
            )
            db.add(link)
            db.flush()

        return user

    _get_or_create_superadmin("Franco",  "Ruiz",   "francoruiz.admin@crm.com",   "ADQSilR4aAKCO%a^")
    _get_or_create_superadmin("Gonzalo", "Maunas", "gonzalomaunas.admin@crm.com", "e&Kr**JtgoK5aNmy")
    db.commit()
    print(f"✅ RBAC Procesado. Se sincronizaron {len(SYSTEM_ENTITIES_REGISTRY)} entidades. Roles: admin, agent, viewer.")


def get_or_create_nomenclator(db, name, parent_ids=None, org_id=ADMIN_ORG_ID):
    """parent_ids: lista de ids de Nomenclator declarados como padre válido
    (feature de nomencladores dependientes, ver docs/nomencladores.md).
    Reemplaza al viejo parent_id único."""
    nom = db.query(Nomenclator).filter_by(name=name, organization_id=org_id).first()
    if not nom:
        nom = Nomenclator(name=name, organization_id=org_id)
        db.add(nom)
        db.flush()
    if parent_ids:
        existing_parent_ids = {p.id for p in nom.parent_nomenclators}
        missing = [pid for pid in parent_ids if pid not in existing_parent_ids]
        if missing:
            parent_objs = db.query(Nomenclator).filter(Nomenclator.id.in_(missing)).all()
            nom.parent_nomenclators = list(nom.parent_nomenclators) + parent_objs
            db.flush()
    return nom

def get_or_create_nomenclator_item(db, nomenclator_id, value, parent_ids=None, org_id=ADMIN_ORG_ID):
    """parent_ids: lista de ids de NomenclatorItem padre (uno por cada
    catálogo padre válido que aplique). Reemplaza al viejo parent_id único."""
    item = db.query(NomenclatorItem).filter_by(value=value, nomenclator_id=nomenclator_id).first()
    if not item:
        item = NomenclatorItem(
            value=value,
            nomenclator_id=nomenclator_id,
            organization_id=org_id,
        )
        db.add(item)
        db.flush()
    if parent_ids:
        existing_parent_ids = {p.id for p in item.parent_items}
        missing = [pid for pid in parent_ids if pid not in existing_parent_ids]
        if missing:
            parent_objs = db.query(NomenclatorItem).filter(NomenclatorItem.id.in_(missing)).all()
            item.parent_items = list(item.parent_items) + parent_objs
            db.flush()
    return item

# -----------------------------------------------------------------------------
# 3. SEED GEOGRAFÍA
# -----------------------------------------------------------------------------
def seed_geography_separated(db):
    print("🌍 Iniciando Seed de Geografía...")

    # 1. Nomencladores Base
    nom_pais = get_or_create_nomenclator(db, "Países")
    nom_prov = get_or_create_nomenclator(db, "Provincias", parent_ids=[nom_pais.id])

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
                value=c_name,
                parent_ids=None
            )

            # Provincias / Estados
            for state in c_states:
                s_name = state['name']

                get_or_create_nomenclator_item(
                    db=db,
                    nomenclator_id=nom_prov.id,
                    value=s_name,
                    parent_ids=[country_item.id]
                )

    except Exception as e:
        print(f"⚠️ Error procesando geografía (puede ser conexión): {e}")
        # No hacemos rollback aquí para no matar los seeds anteriores, solo geografía fallará


def seed_nomenclator_sex(db):
    print("Procesando Nomenclador 'Sexo'...")
    datos = [
        {"value": "Masculino"},
        {"value": "Femenino"},
        {"value": "Otro"},
    ]

    nom_gen = get_or_create_nomenclator(db, "Genero")

    for item in datos:
        get_or_create_nomenclator_item(
            db=db,
            nomenclator_id=nom_gen.id,
            value=item["value"],
            parent_ids=None
        )
