# Build stage
FROM python:3.11-slim

# Evita que Python escriba archivos .pyc en disco y habilita unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Instalar dependencias del sistema requeridas por paquetes C/C++
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto y artefactos requeridos
COPY app ./app
COPY models ./models
COPY sample ./sample
COPY tests ./tests
COPY run.py .

# Crear carpeta de salida
RUN mkdir -p out

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
