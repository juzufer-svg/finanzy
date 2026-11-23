FROM python:3.11-slim

WORKDIR /app

# Los print() del backend (avisos de WhatsApp, errores de Supabase) deben verse al instante en los logs de Railway
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Railway injects $PORT; fallback to 8000 for local use
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
