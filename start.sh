#!/bin/bash
set -e

if [ -f /code/.env ]; then
    export $(grep -v '^#' /code/.env | xargs)
fi

run_tests() {
    echo "🧪 Iniciando suite de tests en background..."
    
    set +e 
    
    PYTHONPATH=/code pytest -vv > /code/test_results.log 2>&1
    
    TEST_EXIT_CODE=$?
    set -e

    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo -e "\n\033[0;32m✅  TODOS LOS TESTS PASARON EXITOSAMENTE \033[0m"
    else
        echo -e "\n\n"
        echo -e "\033[0;33m/=========================================\\"
        echo -e "|  ⚠️   WARNING: TESTS FALLIDOS            |"
        echo -e "|  Revisa test_results.log para detalles  |"
        echo -e "\\=========================================/\033[0m"
        
        # Opcional: Imprimir las últimas 5 líneas del log en consola para dar una pista rápida
        echo -e "\n🔍 Últimas líneas del error:"
        tail -n 10 /code/test_results.log
        echo -e "\n"
    fi
}

if [ "$RUN_TESTS" = "1" ]; then
    run_tests &
fi

echo "🚀 Iniciando servidor FastAPI..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload