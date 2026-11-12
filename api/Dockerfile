FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY migrations ./migrations

# 비root 계정으로 실행. 증적은 /data/evidence 볼륨에 보관한다.
RUN useradd --system --uid 10001 --home /app appuser \
    && mkdir -p /data/evidence && chown -R appuser /data
USER appuser
ENV EVIDENCE_DIR=/data/evidence
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# 스케줄러(APScheduler)가 프로세스 안에서 돌기 때문에 워커는 1개로 고정한다.
CMD ["sh", "-c", "python -m app.migrate && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
