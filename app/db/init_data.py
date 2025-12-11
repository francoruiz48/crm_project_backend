from app.db.session import SessionLocal
from app.models.lead_field_type import LeadFieldType
from app.models.validation_rule_type import ValidationRuleType
from app.models.validation_rule_type_compatibility import ValidationRuleTypeCompatibility

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
        seed_validation_rule_types(db)
        db.commit()
        seed_validation_rule_type_compatibilities(db)
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


def seed_validation_rule_types(db):
    datos = [
        {"code": "MAX_LENGTH","description": "La longitud máxima del campo"},
        {"code": "MIN_LENGTH","description": "La longitud mínima del campo"},
        {"code": "NUMBER_MIN","description": "El valor numérico mínimo permitido"},
        {"code": "NUMBER_MAX","description": "El valor numérico máximo permitido"},
        {"code": "DATE_LESS_THAN_FIELD","description": "Fecha menor que otra fecha en otro campo"},
        {"code": "DATE_GREATER_THAN_FIELD","description": "Fecha mayor que otra fecha en otro campo"},
        {"code": "STRING_REGEX","description": "El texto debe coincidir con una expresión regular"},
        {"code": "REQUIRED_IF_FIELD_EQUALS","description": "El campo es obligatorio si otro campo tiene un valor específico"}
    ]

    seed_generic(db, model = ValidationRuleType, items = datos, unique_by=["code"])

def seed_validation_rule_type_compatibilities(db):
    datos = [
        {"validation_rule_type_code": "MAX_LENGTH", "lead_field_type_code": "STRING"},
        {"validation_rule_type_code": "MIN_LENGTH", "lead_field_type_code": "STRING"},
        {"validation_rule_type_code": "NUMBER_MIN", "lead_field_type_code": "INT"},
        {"validation_rule_type_code": "NUMBER_MAX", "lead_field_type_code": "INT"},
        {"validation_rule_type_code": "NUMBER_MIN", "lead_field_type_code": "NUMBER"},
        {"validation_rule_type_code": "NUMBER_MAX", "lead_field_type_code": "NUMBER"},
        {"validation_rule_type_code": "DATE_LESS_THAN_FIELD", "lead_field_type_code": "DATE"},
        {"validation_rule_type_code": "DATE_GREATER_THAN_FIELD", "lead_field_type_code": "DATE"},
        {"validation_rule_type_code": "STRING_REGEX", "lead_field_type_code": "STRING"},
        {"validation_rule_type_code": "REQUIRED_IF_FIELD_EQUALS", "lead_field_type_code": "STRING"},
    ]

    seed_generic(
        db,
        model=ValidationRuleTypeCompatibility,
        items=datos,
        unique_by=["validation_rule_type_code", "lead_field_type_code"],
        resolve_fk={
            "validation_rule_type_code": (ValidationRuleType, "code"),
            "lead_field_type_code": (LeadFieldType, "code"),
        },
    )