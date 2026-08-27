#!/bin/bash
set -e

if [ -f /code/.env ]; then
    export $(grep -v '^#' /code/.env | xargs)
fi

echo "🚀 Iniciando servidor FastAPI... puerto ${PORT:-8000}..."
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"