FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY rh_meme_watch ./rh_meme_watch
RUN pip install --no-cache-dir .

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin watcher \
 && mkdir -p /data \
 && chown watcher:watcher /data
USER watcher
VOLUME /data

# healthy = the poll loop completed a successful cycle within the last 5 minutes
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import os,sys,time; p='/data/heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 300 else 1)"]

ENTRYPOINT ["python", "-m", "rh_meme_watch"]
