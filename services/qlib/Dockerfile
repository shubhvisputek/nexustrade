FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir grpcio grpcio-tools grpcio-reflection

COPY services/qlib/server.py ./server.py
COPY services/qlib/proto/ ./proto/

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import grpc; ch = grpc.insecure_channel('localhost:50053'); grpc.channel_ready_future(ch).result(timeout=5)" || exit 1

EXPOSE 50053
CMD ["python", "server.py"]
