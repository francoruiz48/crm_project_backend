from sqlalchemy import text
from app.core.constans import DeleteStrategy
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_value import LeadFieldValue
from app.schemas.lead_field_value_schema import LeadFieldValueDetailedResponse, LeadFieldValueResponse

class LeadFieldValueRepository(BaseRepository):
    model = LeadFieldValue
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_out = LeadFieldValueResponse
    schema_out_detail = LeadFieldValueDetailedResponse


    @classmethod
    def initialize_values_for_new_field(cls, session, campaign_id: int, new_field_id: int, default_value: str = None, is_nomenclator: bool = False):
        """
        Backfill optimizado.
        1. Crea registros LeadFieldValue para todos los leads.
        2. Si es Nomenclador con Default, llena la tabla intermedia.
        """
        
        # 1. INSERT EN LEAD_FIELD_VALUE (Siempre se hace)
        # Si NO es nomenclador, el default va en 'value'. Si ES nomenclador, 'value' queda NULL.
        val_col = ":default_val" if (default_value and not is_nomenclator) else "NULL"

        # Usamos RETURNING id para obtener los IDs de los valores recién creados
        # Esto es vital para poder llenar la tabla intermedia después
        # Bug real encontrado 2026-07-30: este INSERT crudo no incluía public_uuid.
        # BaseModelDB.public_uuid tiene un default de Python (uuid.uuid4, ver base_model.py),
        # no un server_default -- un INSERT ... SELECT crudo que bypassea el ORM nunca lo
        # dispara, así que Postgres intentaba insertar NULL en una columna NOT NULL. Esto
        # rompía con 500 (NotNullViolation) cualquier alta de campo nuevo en una campaña que
        # ya tuviera al menos un lead. gen_random_uuid() está disponible en Postgres core
        # desde la v13 (sin necesitar la extensión pgcrypto).
        stmt_values = text(f"""
            INSERT INTO lead_field_value (lead_id, field_id, value, created_at, updated_at, active, public_uuid)
            SELECT
                l.id,
                :field_id,
                {val_col},
                NOW(),
                NOW(),
                true,
                gen_random_uuid()
            FROM lead l
            WHERE l.campaign_id = :campaign_id
            RETURNING id
        """)

        result = session.execute(stmt_values, {
            "field_id": new_field_id,
            "campaign_id": campaign_id,
            "default_val": default_value
        })
        
        # Obtenemos los IDs de los LeadFieldValues creados
        # fetchall devuelve lista de tuplas [(id1,), (id2,)]
        new_value_ids = [row[0] for row in result.fetchall()]

        # 2. INSERT EN TABLA INTERMEDIA (Solo si es Nomenclador y tiene Default)
        if is_nomenclator and default_value and new_value_ids:
            # Asumimos que default_value es el ID del item (int en string)
            try:
                default_item_id = int(default_value)
                
                # Insert masivo en la tabla de asociación
                # Usamos UNNEST para insertar múltiples filas de golpe en Postgres
                stmt_assoc = text("""
                    INSERT INTO lead_field_value_nomenclator (lead_field_value_id, nomenclator_item_id)
                    SELECT unnest(:ids), :item_id
                """)
                
                session.execute(stmt_assoc, {
                    "ids": new_value_ids,
                    "item_id": default_item_id
                })
                
            except ValueError:
                # Si el default no es un entero válido, no insertamos nada en la relación
                pass

        session.flush()