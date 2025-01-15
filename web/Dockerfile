FROM python:3.10.16-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget tar bzip2 gcc g++ git make ccache \
    && pip install --no-cache-dir pexpect future empy==3.3.4 \
    && wget https://firmware.ardupilot.org/Tools/STM32-tools/gcc-arm-none-eabi-10-2020-q4-major-x86_64-linux.tar.bz2 \
    && tar -xjf gcc-arm-none-eabi-10-2020-q4-major-x86_64-linux.tar.bz2 \
    && ln -s -f $(which ccache) /usr/lib/ccache/arm-none-eabi-g++ \
    && ln -s -f $(which ccache) /usr/lib/ccache/arm-none-eabi-gcc

ENV PATH="/usr/lib/ccache/:$PATH:/gcc-arm-none-eabi-10-2020-q4-major/bin/"
COPY . /app
WORKDIR /app/web
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["/bin/sh", "./start.sh"]
