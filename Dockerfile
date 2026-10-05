# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

WORKDIR /app

# Dependências primeiro: essa camada só é refeita quando o requirements muda.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# O painel e o `provas.json` do servidor são gravados em runtime, então o
# processo precisa poder escrever neles sem ser root.
RUN useradd --create-home --uid 10001 aura \
 && mkdir -p /app/dados \
 && chown -R aura:aura /app
USER aura

ENV WEB_PANEL_HOST=0.0.0.0 \
    WEB_PANEL_PORT=2501 \
    MONGO_DB_NAME=aura_bot

VOLUME ["/app/dados"]

EXPOSE 2501

HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('WEB_PANEL_PORT','2501')+'/health',timeout=8).read()" || exit 1

CMD ["python", "main.py"]