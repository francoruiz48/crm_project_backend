from app.db.session import SessionLocal
from app.models.lead_field_type import LeadFieldType

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


