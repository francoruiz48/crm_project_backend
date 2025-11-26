from app.db.session import SessionLocal
from app.models.lead_field_type import LeadFieldType

def seed_lead_field_types():
    db = SessionLocal()
    tipos = [
        {"code": "STRING", "description": "Texto"},
        {"code": "INT", "description": "Número entero"},
        {"code": "DATE", "description": "Fecha"},
        {"code": "BOOL", "description": "Valor verdadero/falso"},
    ]

    for t in tipos:
        exists = db.query(LeadFieldType).filter_by(code=t["code"]).first()
        if not exists:
            db.add(LeadFieldType(**t))

    db.commit()
    db.close()
