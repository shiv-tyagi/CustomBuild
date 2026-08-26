FROM ardupilot/ardupilot-dev-chibios:v0.1.5

RUN groupadd -g 999 ardupilot && \
    useradd -u 999 -g 999 -m ardupilot --shell /bin/false && \
    mkdir /app && \
    chown ardupilot:ardupilot /app && \
    mkdir /workdir && \
    chown ardupilot:ardupilot /workdir

COPY builder/requirements.txt /app/builder/requirements.txt
RUN pip install --no-cache-dir -r /app/builder/requirements.txt

COPY --chown=ardupilot:ardupilot ap_git /app/ap_git
COPY --chown=ardupilot:ardupilot build_config /app/build_config
COPY --chown=ardupilot:ardupilot build_manager /app/build_manager
COPY --chown=ardupilot:ardupilot builder /app/builder
COPY --chown=ardupilot:ardupilot metadata_manager /app/metadata_manager
COPY --chown=ardupilot:ardupilot utils /app/utils
COPY --chown=ardupilot:ardupilot schemas /app/schemas

WORKDIR /app
USER ardupilot
CMD ["python", "-m", "builder"]
