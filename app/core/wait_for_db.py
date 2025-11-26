import time
import psycopg2
from psycopg2 import OperationalError
from app.core.config import settings

def wait_for_db(retries=10, delay=3):
    """Espera a que la base de datos esté lista antes de iniciar FastAPI"""
    while retries > 0:
        try:
            conn = psycopg2.connect(
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
            )
            conn.close()
            print("✅ Database is ready!")
            return
        except OperationalError:
            retries -= 1
            print(f"⏳ Database not ready, waiting {delay}s... retries left: {retries}")
            time.sleep(delay)
    raise Exception("❌ Could not connect to the database after multiple retries")
