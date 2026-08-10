from typing import Optional
from fastapi import HTTPException, status
from app.core.constans import INITIAL_ROUTES_STATES, INITIAL_STATES, SystemAuditLogAction, ADMIN_ORG_ID
from app.models.lead_contact_state import LeadContactState
from app.models.lead_field_section import LeadFieldSection
from app.services.base_service import BaseService
from app.db.repository.organization_repository import OrganizationRepository
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.core.security import UserContext
from app.models.security_models import Role, UserOrganization


class OrganizationService(BaseService):
    repository = OrganizationRepository

    @classmethod
    def _create_default_contact_states(cls, session, org_id: int):

        """Crea estados de contacto predeterminados para la organización"""
        default_contact_states = [
            {"name": "No Contactado", "color": "#6B7280", "is_initial": True, "order": 1},   
            {"name": "Esperando Respuesta", "color": "#8B5CF6", "is_initial": False, "order": 2},    
            {"name": "En Conversación", "color": "#3B82F6", "is_initial": False, "order": 3},     
            {"name": "Rechazado", "color": "#BE0D0D", "is_initial": False, "order": 4},
        ]
        
        for state_data in default_contact_states:
            new_state = LeadContactState(
                name=state_data["name"],
                color=state_data["color"],
                is_initial=state_data["is_initial"],
                order=state_data["order"],
                organization_id=org_id
            )
            session.add(new_state)

    @classmethod
    def _create_default_sections(cls, session, org_id: int):

        """Crea secciones de campos predeterminadas para la organización"""
        default_sections = [
            {"name": "Información básica"},
        ]
        
        for section_data in default_sections:
            new_section = LeadFieldSection(
                name=section_data["name"],
                organization_id=org_id
            )
            session.add(new_section)

    @classmethod
    def _create_default_lead_flow(cls, session, org_id: int, user_context: Optional[UserContext] = None):
        """Genera un embudo de ventas genérico para la nueva organización"""
        created_by = user_context.user.id if user_context and user_context.user else None
        # 1. Crear el Flujo Base
        flow = LeadFlow(name="Flujo de Ventas Predeterminado", organization_id=org_id, created_by=created_by)
        session.add(flow)
        session.flush() # Necesario para obtener flow.id

        # 2. Definir los Estados
        states_data = INITIAL_STATES

        created_states = []
        for data in states_data:
            state = LeadState(lead_flow_id=flow.id, organization_id=org_id, created_by=created_by, **data)
            session.add(state)
            created_states.append(state)
        
        session.flush() # Obtenemos los IDs de todos los estados

        # 3. Construir el Grafo (Las Transiciones)
        # Índices: 0(Ing), 1(Cont), 2(Reu), 3(Prop), 4(Venta), 5(NoInt)
        routes = INITIAL_ROUTES_STATES

        for from_idx, to_idx in routes:
            transition = LeadStateTransition(
                lead_flow_id=flow.id,
                from_state_id=created_states[from_idx].id,
                to_state_id=created_states[to_idx].id,
                created_by=created_by
            )
            session.add(transition)

    @classmethod
    def _clone_default_roles_for_org(cls, session, org_id: int):
        """Clona las plantillas globales de roles (admin, agent, viewer) para la nueva org."""
        templates = session.query(Role).filter_by(organization_id=ADMIN_ORG_ID).all()
        cloned = {}
        for template in templates:
            existing = session.query(Role).filter_by(
                code=template.code, organization_id=org_id
            ).first()
            if not existing:
                new_role = Role(
                    name=template.name,
                    code=template.code,
                    organization_id=org_id,
                )
                new_role.permissions = list(template.permissions)
                session.add(new_role)
                session.flush()
                cloned[template.code] = new_role
            else:
                cloned[template.code] = existing
        return cloned

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None, **kwargs):
        def do_create(uow):
            from fastapi import HTTPException, status
            user_id = user_context.user.id if user_context and user_context.user else None
            is_superuser = user_context.is_superuser if user_context else False

            # Validar límite: usuarios comunes solo pueden ser owner de 1 organización
            if user_id and not is_superuser:
                existing_owned = uow.session.query(UserOrganization).filter_by(
                    user_id=user_id,
                    is_owner=True,
                ).first()
                if existing_owned:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Ya sos propietario de una organización. Solo se permite una por usuario.",
                    )

            # 1. Creamos la organización normalmente
            org_data = obj_in.model_dump(exclude_unset=True)
            org_data.update(kwargs)
            org = cls.repository.create(uow.session, org_data, user_context=user_context)
            uow.session.flush()  # Obligatorio para tener org.id

            # org.id es el schema Pydantic (cls.repository.create() devuelve
            # schema_out_detail.model_validate(...), Fase 3) -- .id YA es el public_uuid (str),
            # no el id interno. Los helpers de abajo hacen INSERTs crudos con organization_id
            # como columna Integer real (FK), así que hay que resolver el uuid al id interno acá
            # UNA vez -- antes se pasaba org.id (uuid) directo y explotaba con
            # "invalid input syntax for type integer" en el primer INSERT (lead_flow), rompiendo
            # TODO POST /organizations/ (bug preexistente, no de esta sesión, ver backend/AGENTS.md
            # §18-octies).
            org_internal_id = cls.repository.get_internal_id_by_public_uuid(uow.session, org.id)

            # 2. Inyectar el flujo por defecto
            cls._create_default_lead_flow(uow.session, org_internal_id, user_context=user_context)

            cls._create_default_contact_states(uow.session, org_internal_id)

            cls._create_default_sections(uow.session, org_internal_id)

            # 3. Clonar roles plantilla para esta org
            cloned_roles = cls._clone_default_roles_for_org(uow.session, org_internal_id)

            # 4. Coronar al creador como owner y asignarle el rol admin de la org
            if user_id:
                user_org = UserOrganization(
                    user_id=user_id,
                    organization_id=org_internal_id,
                    is_owner=True,
                )
                uow.session.add(user_org)
                uow.session.flush()

                admin_role = cloned_roles.get("admin")
                if admin_role:
                    user_org.roles = [admin_role]

            # LOG DE AUDITORÍA (internal_id ya resuelto arriba, evita resolverlo de nuevo)
            cls._log_audit(uow.session, org, action=SystemAuditLogAction.CREATED, changes=org_data, user_id=user_id, internal_id=org_internal_id)

            return org

        return cls._execute(action="Crear Organización", func=do_create)

    # =========================================================================
    # Hallazgo #15 (2026-07-11): OrganizationRepository.apply_security_filter
    # (el gatekeeper que usa BaseService.update/delete/deactivate/set_active vía
    # get_by_id) deja pasar CUALQUIER organización de la que el usuario sea
    # miembro, sin importar el header X-Organization-Id. El chequeo de PERMISO
    # (PermissionChecker en la ruta) sí valida contra la org del header. Como
    # son dos criterios distintos, un usuario miembro de dos o más orgs podía
    # editar la organización donde tiene un rol menor mandando el header de la
    # organización donde sí tiene el permiso `organization:update`.
    #
    # Fix: exigir acá, antes de delegar en el genérico, que la organización que
    # se va a mutar sea exactamente la organización activa del request
    # (user_context.organization_id, que a su vez sale del header — ver
    # get_current_user_roles en app/core/security.py). El superadmin no tiene
    # esta restricción, igual que ya pasa en apply_security_filter.
    # =========================================================================
    @classmethod
    def _assert_active_org(cls, internal_id: int, user_context: Optional[UserContext] = None):
        """internal_id ya viene resuelto (id interno, no el public_uuid) por el caller."""
        if user_context is None or user_context.is_superuser:
            return
        if user_context.organization_id != internal_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para modificar esta organización desde el contexto actual.",
            )

    @classmethod
    def _resolve_or_404(cls, obj_id: str) -> int:
        from app.db.unit_of_work import UnitOfWork
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
        if internal_id is None:
            cls._not_found(obj_id)
        return internal_id

    @classmethod
    def update(cls, obj_id: str, obj_data, user_context: Optional[UserContext] = None):
        internal_id = cls._resolve_or_404(obj_id)
        cls._assert_active_org(internal_id, user_context)
        return super().update(obj_id, obj_data, user_context=user_context)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        internal_id = cls._resolve_or_404(obj_id)
        cls._assert_active_org(internal_id, user_context)
        return super().delete(obj_id, user_context=user_context, force=force)

    @classmethod
    def deactivate(cls, obj_id: str, user_context: Optional[UserContext] = None):
        internal_id = cls._resolve_or_404(obj_id)
        cls._assert_active_org(internal_id, user_context)
        return super().deactivate(obj_id, user_context=user_context)

    @classmethod
    def set_active(cls, obj_id: str, user_context: Optional[UserContext] = None):
        internal_id = cls._resolve_or_404(obj_id)
        cls._assert_active_org(internal_id, user_context)
        return super().set_active(obj_id, user_context=user_context)

    @classmethod
    def _partition_ids_by_active_org(cls, obj_ids: list, user_context: Optional[UserContext] = None):
        """Versión bulk de _assert_active_org: separa los ids en (permitidos,
        bloqueados) según si coinciden con la organización activa del request
        (o todos permitidos si es superadmin) — mismo criterio, sin cortar toda
        la operación por un solo id ajeno en el lote. obj_ids llega como lista de
        public_uuid; se resuelven a id interno solo para la comparación, pero lo
        que se devuelve son los UUIDs originales (BaseService los vuelve a resolver)."""
        if user_context is None or user_context.is_superuser:
            return list(obj_ids), []
        from app.db.unit_of_work import UnitOfWork
        with UnitOfWork() as uow:
            uuid_to_internal_id = cls.repository.get_internal_ids_by_public_uuids(uow.session, obj_ids)
        allowed = [oid for oid in obj_ids if uuid_to_internal_id.get(oid) == user_context.organization_id]
        blocked = [oid for oid in obj_ids if uuid_to_internal_id.get(oid) != user_context.organization_id]
        return allowed, blocked

    @classmethod
    def bulk_delete(cls, obj_ids: list, user_context: Optional[UserContext] = None):
        allowed_ids, blocked_ids = cls._partition_ids_by_active_org(obj_ids, user_context)
        result = (
            super().bulk_delete(allowed_ids, user_context=user_context)
            if allowed_ids else {"deleted": [], "disabled": [], "failed": []}
        )
        result["failed"] = result.get("failed", []) + blocked_ids
        return result

    @classmethod
    def bulk_set_active(cls, obj_ids: list, user_context: Optional[UserContext] = None):
        allowed_ids, blocked_ids = cls._partition_ids_by_active_org(obj_ids, user_context)
        result = (
            super().bulk_set_active(allowed_ids, user_context=user_context)
            if allowed_ids else {"activated": [], "already_active": [], "failed": []}
        )
        result["failed"] = result.get("failed", []) + blocked_ids
        return result