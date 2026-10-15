FROM python:3.12-slim
RUN groupadd --gid 10001 app && groupadd --gid 10002 student \
    && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin student
COPY supervisor.py /opt/supervisor.py
CMD ["python3", "/opt/supervisor.py"]
