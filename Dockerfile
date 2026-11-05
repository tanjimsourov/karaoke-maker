FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 libgl1 fonts-dejavu-core fonts-liberation \
    ca-certificates git build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements-zoom.txt requirements-demucs.txt requirements-separation-extra.txt setup.py .env.example ./
# Keep the existing two isolated Python environments; default to CPU wheels.
RUN python setup.py --check && python -m venv .venv-zoom && python -m venv .venv-demucs \
    && .venv-zoom/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 \
    && .venv-demucs/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 \
    && .venv-zoom/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-zoom.txt \
    && .venv-demucs/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-demucs.txt
# WhisperX sentence alignment needs these data packages, not just the nltk library.
# Store them in the image (outside writable model/work volumes and cleanup paths).
ENV NLTK_DATA=/opt/nltk_data
RUN .venv-zoom/bin/python -c "import nltk; nltk.download('punkt', download_dir='/opt/nltk_data', raise_on_error=True); nltk.download('punkt_tab', download_dir='/opt/nltk_data', raise_on_error=True); nltk.data.find('tokenizers/punkt_tab/english/')"
COPY karaoke.py ./
COPY tools/ ./tools/
COPY config/ ./config/
COPY assets/ ./assets/
ENV KARAOKE_SERVER_CONTAINER=1 KARAOKE_PROJECT_ROOT=/app KARAOKE_FFMPEG=/usr/bin/ffmpeg \
    KARAOKE_DEMUCS_PYTHON=/app/.venv-demucs/bin/python \
    KARAOKE_WORK_DIR=/app/work/local_open_source KARAOKE_OUTPUT_DIR=/app/out \
    KARAOKE_MODEL_DIR=/app/models HF_HOME=/app/models/huggingface TORCH_HOME=/app/models/torch \
    TMPDIR=/app/tmp \
    XDG_CACHE_HOME=/app/models/cache MPLCONFIGDIR=/app/tmp/matplotlib \
    KARAOKE_LOGO=/app/assets/logo-karaoke-cmyk-transparent.png \
    KARAOKE_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
RUN useradd --create-home --uid 10001 karaoke \
    && mkdir -p /app/work /app/out /app/reports /app/models /app/tmp \
    && chown karaoke:karaoke /app/work /app/out /app/reports /app/models /app/tmp
USER karaoke
RUN .venv-zoom/bin/python -c "import nltk; assert len(nltk.sent_tokenize('First sentence. Second sentence.')) == 2; print('NLTK tokenizer OK')"
RUN .venv-zoom/bin/python -c "import sys,subprocess; sys.path.insert(0,'tools'); from project_runtime import DEMUCSPY; assert str(DEMUCSPY)=='/app/.venv-demucs/bin/python'; subprocess.run([str(DEMUCSPY),'-c','import numpy,torch,demucs; print(\"Demucs environment OK\")'],check=True)"
ENTRYPOINT ["/app/.venv-zoom/bin/python", "-u", "/app/tools/server_batch.py"]
CMD []
