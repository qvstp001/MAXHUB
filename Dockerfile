FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data LIBRARY_ROOTS=/media PORT=8096 ADMIN_PASSWORD=qmaxhub123456
WORKDIR /app
COPY qmaxhub ./qmaxhub
COPY web ./web
RUN groupadd --gid 10001 qmaxhub && useradd --uid 10001 --gid qmaxhub --no-create-home qmaxhub && mkdir -p /data /media && chown qmaxhub:qmaxhub /data
USER qmaxhub
EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD ["python", "-m", "qmaxhub.healthcheck"]
CMD ["python", "-m", "qmaxhub"]
