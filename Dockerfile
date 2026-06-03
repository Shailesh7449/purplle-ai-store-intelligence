# Single image used for api / consumer / pipeline (command chosen in compose).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# OpenCV / ultralytics runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Install CPU-ONLY PyTorch first (no CUDA/GPU libs -> ~5 GB smaller image).
#    This is the key to keeping the image small on a laptop without an NVIDIA GPU.
RUN pip install --no-cache-dir \
    torch==2.4.1 torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cpu

# 2) Now install the rest. torch is already satisfied, so ultralytics won't
#    pull the heavy CUDA build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn backend.main_lite:app --host 0.0.0.0 --port ${PORT:-8000}
