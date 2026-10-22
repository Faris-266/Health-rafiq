FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
ENV RAFIQ_DB=/data/rafiq.db
VOLUME /data
EXPOSE 8000
# One worker: the scheduler loop lives in-process. Scale out by moving it to a separate job + Postgres (see README).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "5"]
