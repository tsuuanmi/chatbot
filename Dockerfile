ARG HAYHOOKS_IMAGE=deepset/hayhooks@sha256:2d657aa5499f440ccae17c860d35d1d709095b385da3ec9338ebc0decdb37ce9
FROM ${HAYHOOKS_IMAGE}

USER root

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

ARG EMBEDDING_MODEL
ARG EMBEDDING_DIMENSION

ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    EMBEDDING_DIMENSION=${EMBEDDING_DIMENSION} \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed

# Download the embedding model once while building the release image.
RUN python - <<'PY'
import os

from fastembed import TextEmbedding

model = TextEmbedding(
    model_name=os.environ["EMBEDDING_MODEL"],
    cache_dir=os.environ["FASTEMBED_CACHE_PATH"],
)

embedding = next(iter(model.embed(["kiểm tra mô hình embedding"])))

expected = int(os.environ["EMBEDDING_DIMENSION"])
actual = len(embedding)

if actual != expected:
    raise RuntimeError(
        f"Unexpected embedding dimension: expected={expected}, actual={actual}"
    )

print(f"Embedding model ready: dimension={actual}")
PY

RUN groupadd --gid 10001 chatbot \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --home-dir /home/chatbot \
        --shell /usr/sbin/nologin \
        chatbot \
    && chown -R 10001:10001 /opt/models/fastembed

COPY --chown=10001:10001 chatbot_app /app/chatbot_app
COPY --chown=10001:10001 data/policies /app/data/policies
COPY --chown=10001:10001 tools/__init__.py /app/tools/__init__.py
COPY --chown=10001:10001 tools/index_knowledge.py /app/tools/index_knowledge.py
COPY --chown=10001:10001 tools/index_figures.py /app/tools/index_figures.py

ENV PYTHONPATH=/app \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

USER 10001:10001
