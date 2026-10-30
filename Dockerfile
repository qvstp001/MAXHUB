FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data LIBRARY_ROOTS=/media PORT=8096
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY maxhub ./maxhub
COPY web ./web
COPY LICENSE ./LICENSE
LABEL org.opencontainers.image.title="MAXHUB" org.opencontainers.image.licenses="AGPL-3.0-or-later"
RUN groupadd --gid 10001 maxhub && useradd --uid 10001 --gid maxhub --no-create-home maxhub && mkdir -p /data /media && chown maxhub:maxhub /data
USER maxhub
EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD ["python", "-m", "maxhub.healthcheck"]
CMD ["python", "-m", "maxhub"]
