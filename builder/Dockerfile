FROM ardupilot/ardupilot-dev-chibios:v0.1.3

COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir -r ./builder/requirements.txt

CMD ["python", "-m", "builder"]
