from app.core.error_messages import ERROR_NOT_FOUND
from app.core.exceptions import NotFoundException
from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.schemas.lead_schema import LeadResponse
from app.models.lead_field_value import LeadFieldValue
from app.models.lead_field import LeadField
from app.db.session import SessionLocal
from sqlalchemy import and_

class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse

    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
    ]

    @classmethod
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, campaign_id: int = None):
        # 1. Construcción Personalizada de la Query
        query = session.query(cls.model)

        # --- Tu Lógica Especial ---
        if campaign_id is not None:
            query = query.filter(cls.model.campaign_id == campaign_id)
        # --------------------------

        # Lógica estándar de 'active'
        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        # 2. Ejecución Consistente (Reutilizando la lógica del padre)
        return cls._execute_read_query(query, detailed)

    @classmethod
    def find_duplicate(cls, session, campaign_id: int, primary_values: dict) -> bool:
        """
        Busca si existe algún Lead en la campaña que coincida EXACTAMENTE
        con TODOS los valores primarios pasados.
        primary_values = {field_id: 'valor', field_id_2: 'valor_2'}
        """
        if not primary_values:
            return False

        # Empezamos buscando leads de esa campaña
        query = session.query(cls.model).filter(cls.model.campaign_id == campaign_id)

        # Iteramos dinámicamente sobre cada campo primario (AND lógico)
        for f_id, val in primary_values.items():
            # Filtramos leads que tengan un valor asociado que coincida
            query = query.filter(
                cls.model.field_values.any(
                    and_(
                        LeadFieldValue.field_id == f_id,
                        LeadFieldValue.value == str(val) # Comparamos como string
                    )
                )
            )

        # Si existe al menos uno, es duplicado
        return query.first() is not None

    @classmethod
    def upsert_values(cls, session, lead_id: int, values: list):
        cls.upsert_children(
            session=session,
            parent_model=Lead,
            parent_id=lead_id,
            relation_name="field_values",
            items=values,
            key_attr="field_id",
            # CORRECCIÓN AQUÍ:
            create_fn=lambda item: LeadFieldValue(
                lead_id=lead_id, 
                **item.dict()     
            )
        )

    @classmethod
    def has_leads_in_campaign(cls, session, campaign_id: int) -> bool:
        """Devuelve True si existe al menos un lead en la campaña."""
        # Usamos limit(1) para que sea ultra rápido, no necesitamos contar todos
        return session.query(cls.model.id).filter(cls.model.campaign_id == campaign_id).limit(1).first() is not None
