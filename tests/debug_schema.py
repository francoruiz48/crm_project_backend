import sys
import os
from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.models.lead_field_value import LeadFieldValue # Importar el modelo

def check_reality():
    print("\n🕵️‍♂️ --- INICIO DIAGNÓSTICO ---")
    
    # 1. VERIFICAR CÓDIGO FUENTE (Lo que ve Python dentro de Docker)
    file_path = "/code/app/models/lead_field_value.py"
    print(f"\n📂 1. Inspeccionando archivo: {file_path}")
    try:
        with open(file_path, "r") as f:
            content = f.read()
            if "value = Column(String" in content:
                print("   ✅ CÓDIGO OK: La columna 'value' está definida como STRING.")
            elif "value = Column(Integer" in content:
                print("   ❌ CÓDIGO MAL: La columna 'value' sigue definida como INTEGER.")
            else:
                print("   ⚠️ CÓDIGO: No pude determinar el tipo. Contenido de la línea:")
                for line in content.splitlines():
                    if "value =" in line:
                        print(f"      -> {line.strip()}")
    except Exception as e:
        print(f"   ❌ Error leyendo archivo: {e}")

    # 2. VERIFICAR BASE DE DATOS (La verdad absoluta)
    TEST_DB_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/crm_test_db"
    print(f"\n🔌 2. Conectando a la DB: {TEST_DB_URL}")
    
    try:
        engine = create_engine(TEST_DB_URL)
        inspector = inspect(engine)
        columns = inspector.get_columns("lead_field_value")
        
        col_def = next((c for c in columns if c["name"] == "value"), None)
        
        if col_def:
            tipo_real = str(col_def["type"]).upper()
            print(f"   📊 BASE DE DATOS: La columna 'value' es de tipo: {tipo_real}")
            
            if "VARCHAR" in tipo_real or "STRING" in tipo_real or "TEXT" in tipo_real:
                print("   ✅ CONCLUSIÓN: La DB está correcta (String).")
            else:
                print("   ❌ CONCLUSIÓN: La DB tiene el tipo INCORRECTO (Integer).")
        else:
            print("   ❌ La columna 'value' NO EXISTE en la tabla.")
            
    except Exception as e:
        print(f"   ❌ Error conectando a la DB: {e}")

if __name__ == "__main__":
    check_reality()