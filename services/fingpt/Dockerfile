FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir grpcio grpcio-tools grpcio-reflection

COPY services/fingpt/server.py ./server.py
COPY services/fingpt/proto/ ./proto/

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import grpc; ch = grpc.insecure_channel('localhost:50052'); grpc.channel_ready_future(ch).result(timeout=5)" || exit 1

EXPOSE 50052
CMD ["python", "server.py"]
