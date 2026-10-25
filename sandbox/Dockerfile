FROM python:3.12-slim
# JDK (javac/java) and gcc (cc) let the runner compile and run student Java and C, not just Python.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 app && groupadd --gid 10002 student \
    && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin student
COPY supervisor.py /opt/supervisor.py
CMD ["python3", "/opt/supervisor.py"]
