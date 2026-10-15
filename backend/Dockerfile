FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# The embedding weights are fetched once at build time and baked into the image, so the running
# containers never download anything (TR-L-02). They are never committed to git.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
COPY app/retrieval/model_name.py /tmp/model_name.py
RUN python -c "import sys; sys.path.insert(0, '/tmp'); from model_name import MODEL_NAME; \
from fastembed import TextEmbedding; TextEmbedding(MODEL_NAME, cache_dir='/opt/fastembed')" \
    && rm /tmp/model_name.py && chmod -R a+rX /opt/fastembed
ENV HF_HUB_OFFLINE=1

COPY . .
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --system app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
