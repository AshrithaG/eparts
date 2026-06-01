# eParts ML inference service (M7) — CAP-ML-01 containerization.
#
# CPU-only image. Heavy artifacts (faiss.bin, cluster_cov.npz,
# centroids.parquet, sigma_table.parquet) are NOT baked into the image —
# they are mounted at runtime from a volume at /artifacts so the image
# stays small and artifacts can be swapped without a rebuild.
#
# Build:
#   docker build -t eparts-ml:v1 .
# Run (mount the run directory + config):
#   docker run -p 8000:8000 \
#       -v /path/to/artifacts/v1/current:/artifacts:ro \
#       -v /path/to/config:/app/config:ro \
#       eparts-ml:v1
#
# the_standard_data/ (1B for the PT map, 2A for the usage prior) must also
# be mounted — see the README for the full volume layout.

FROM python:3.12-slim

WORKDIR /app

# System deps: none required for the inference path (OCR/tesseract is only
# for the archived Layer 1 prototype, not the service).

COPY requirements.txt .
# Install the CPU torch wheel explicitly to avoid pulling CUDA.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

EXPOSE 8000

# Artifacts mounted at /artifacts; 1B/2A mounted under the_standard_data/.
ENV EPARTS_RUN_DIR=/artifacts

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["python", "scripts/m7_serve.py", "--host", "0.0.0.0", "--run-dir", "/artifacts"]
