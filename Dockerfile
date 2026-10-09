FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Usuário sem privilégios. /data já nasce com o dono certo, então volumes
# nomeados novos herdam essa permissão.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir /data && chown app:app /data

COPY app ./app

# FORWARDED_ALLOW_IPS é lido pelo uvicorn: IPs do proxy reverso cujos
# X-Forwarded-For/Proto são confiáveis. Use "*" só se a porta não ficar exposta.
ENV DB_PATH=/data/vendas.db \
    FORWARDED_ALLOW_IPS=127.0.0.1

VOLUME /data
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
