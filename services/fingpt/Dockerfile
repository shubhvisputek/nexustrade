FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    transformers \
    peft \
    bitsandbytes \
    grpcio \
    grpcio-tools

EXPOSE 50052

CMD ["python", "-m", "nexustrade"]
