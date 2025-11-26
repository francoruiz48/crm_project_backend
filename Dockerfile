# Imagen base de Python
FROM python:3.11

# Crear un directorio de trabajo dentro del contenedor
WORKDIR /code
ENV PYTHONPATH=/code

# Copiar el archivo de requerimientos e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la app
COPY ./app /code/app
COPY ./tests /code/tests
COPY start.sh /code/start.sh

# Dar permisos de ejecución al script
RUN chmod +x /code/start.sh

# Comando por defecto: correr el script de inicio
CMD ["/code/start.sh"]
