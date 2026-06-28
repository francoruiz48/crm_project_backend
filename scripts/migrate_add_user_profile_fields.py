"""
migrate_add_user_profile_fields.py
===================================
Agrega last_name, phone y date_of_birth a la tabla 'user'.
Ejecutar UNA sola vez sobre una DB existente (si creás la DB desde cero
este script no es necesario ya que create_all genera las columnas).

Uso:
    cd backend
    python scripts/migrate_add_user_profile_fields.py
"""

from app.db.session import engine
from sqlalchemy import text

MIGRATIONS = [
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_name VARCHAR;',
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS phone VARCHAR;',
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS date_of_birth DATE;',
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
