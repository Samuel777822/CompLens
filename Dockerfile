# CompLens container. Works on any server that runs Docker (amd64 or arm64).
# Build order is chosen so that changing only your code rebuilds in seconds:
# the big layers (PyTorch, the OCR models) are cached and reused.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# run as a normal user, not root
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# 1) PyTorch, CPU-only build (about 200 MB instead of 2 GB+ for the GPU build)
RUN pip install --user torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 2) the other Python libraries
COPY --chown=user requirements.txt .
RUN pip install --user -r requirements.txt

# 3) download the OCR models NOW (build time), so a restart never has to download anything
RUN python -c "import easyocr; easyocr.Reader(['en','hi'], gpu=False); easyocr.Reader(['en'], gpu=False)"

# 4) your code (this is the only layer that changes when you edit the app)
COPY --chown=user . .

ENV PORT=8000
EXPOSE 8000

# the server answers /health within a second even while the OCR models are still loading
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8000'), timeout=4)"

# ONE worker on purpose: the OCR models (about 1.5 GB of RAM each copy) are loaded once and shared.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
