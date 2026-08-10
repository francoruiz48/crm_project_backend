"""
migrate_add_subtitle_order.py
===================================
Agrega subtitle_order a la tabla 'lead_field' (igual mecanismo que title_order, pero para el
subtítulo: línea secundaria debajo del título, ej. Cargo + Empresa).
Ejecutar UNA sola vez sobre una DB existente (si creás la DB desde cero este script no es
necesario ya que create_all genera la columna).

Uso:
    cd backend
    python scripts/migrate_add_subtitle_order.py
"""

from app.db.session import engine
from sqlalchemy import text

MIGRATIONS = [
    'ALTER TABLE "lead_field" ADD COLUMN IF NOT EXISTS subtitle_order INTEGER;',
]

def run():
    with engine.connect() as conn:
        for stmt in MIGRATIONS:
            print(f"  ▶  {stmt}")
            conn.execute(text(stmt))
        conn.commit()
    print("✅ Migración completada.")

if __name__ == "__main__":
    run()
