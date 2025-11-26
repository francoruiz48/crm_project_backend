#!/bin/bash
set -e

# Cargar variables de entorno desde .env
if [ -f /code/.env ]; then
    export $(grep -v '^#' /code/.env | xargs)
fi

# Ejecutar tests si RUN_TESTS=1
if [ "$RUN_TESTS" = "1" ]; then
    echo "=============================="
    echo "Ejecutando tests automatizados en background"
    echo "=============================="
    PYTHONPATH=/code pytest /code/tests/ -v 2>&1 | tee /code/test_results.log || true &
fi

# Iniciar el servidor FastAPI normalmente
echo "=============================="
echo "Iniciando servidor FastAPI..."
echo "=============================="
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
