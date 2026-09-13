FROM node:24-alpine AS frontend
WORKDIR /src/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libegl1 libopengl0 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY services/ services/
COPY shared/ shared/
COPY robot/ robot/
COPY integrations/ integrations/
COPY sim/ sim/
COPY ml/ ml/
COPY data/source-registry/ data/source-registry/
COPY data/patient-feedback/ data/patient-feedback/
COPY data/hospital-images/ data/hospital-images/
COPY --from=frontend /src/apps/web/dist apps/web/dist/
RUN useradd --uid 10001 --create-home vela && mkdir -p runtime artifacts && chown -R vela:vela /app
USER 10001
ENV VELA_DEMO_MODE=0 MUJOCO_GL=egl
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "services.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

