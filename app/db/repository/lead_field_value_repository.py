from sqlalchemy import text
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_value import LeadFieldValue
from app.schemas.lead_field_value_schema import LeadFieldValueDetailedResponse, LeadFieldValueResponse

class LeadFieldValueRepository(BaseRepository):
    model = LeadFieldValue
    schema_out = LeadFieldValueResponse
    schema_out_detail = LeadFieldValueDetailedResponse


    @classmethod
    def initialize_values_for_new_field(cls, session, campaign_id: int, new_field_id: int, default_value: str = None, is_nomenclator: bool = False):
        """
        Crea registros LeadFieldValue para TODOS los leads existentes de una campaña.
        Usa INSERT INTO ... SELECT para máxima eficiencia.
        """
        
        # Definimos dónde guardar el valor (value o nomenclator_item_id)
        if is_nomenclator and default_value:
            val_col = "NULL"
            nom_col = ":default_val" # Si es nomenclador, el default_value es el ID del item
        else:
            val_col = ":default_val"
            nom_col = "NULL"

        # SQL Crudo optimizado: 
        # Inserta en field_values SELECCIONANDO todos los IDs de la tabla LEAD de esa campaña.
        stmt = text(f"""
            INSERT INTO lead_field_value (lead_id, field_id, value, nomenclator_item_id, created_at, updated_at, active)
            SELECT 
                l.id, 
                :field_id, 
                {val_col}, 
                {nom_col}, 
                NOW(), 
                NOW(), 
                true
            FROM lead l
            WHERE l.campaign_id = :campaign_id
        """)

        session.execute(stmt, {
            "field_id": new_field_id,
            "campaign_id": campaign_id,
            "default_val": default_value
        })
        session.flush()