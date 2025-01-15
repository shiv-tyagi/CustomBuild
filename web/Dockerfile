FROM python:3.10.16-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git

COPY . /app
WORKDIR /app/web
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["/bin/sh", "./start.sh"]
