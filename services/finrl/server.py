"""FinRL gRPC stub server.

Returns mock predictions for development and testing.
The real implementation would load a trained FinRL model.
"""

from __future__ import annotations

import logging
import random
from concurrent import futures

logger = logging.getLogger(__name__)

try:
    import grpc
    from grpc_reflection.v1alpha import reflection

    _HAS_GRPC = True
except ImportError:
    _HAS_GRPC = False
    logger.warning("grpc not installed — FinRL server will not start")


# ---------------------------------------------------------------------------
# Stub servicer (mock responses)
# ---------------------------------------------------------------------------

if _HAS_GRPC:

    class FinRLServicer:
        """Mock FinRL servicer that returns random predictions."""

        def Predict(self, request, context):  # noqa: N802
            """Return a mock action and confidence.

            In production this would:
            1. Load the FinRL model specified by request.model_name
            2. Feed request.observation through the policy network
            3. Return the recommended action and confidence
            """
            # Lazy import to avoid import errors when proto stubs aren't compiled
            action = random.uniform(-1.0, 1.0)  # -1 = sell, 0 = hold, +1 = buy
            confidence = random.uniform(0.3, 0.9)
            model_name = request.model_name or "ppo_default"

            logger.info(
                "FinRL Predict: symbol=%s model=%s action=%.3f confidence=%.3f",
                request.symbol,
                model_name,
                action,
                confidence,
            )

            # Build response without compiled proto — use generic message
            # When proto is compiled, replace with finrl_pb2.PredictResponse(...)
            response = type("PredictResponse", (), {
                "action": action,
                "confidence": confidence,
                "model_name": model_name,
            })()
            return response


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def serve(port: int = 50051) -> None:
    """Start the FinRL gRPC server on the given port."""
    if not _HAS_GRPC:
        logger.error("Cannot start FinRL server: grpc is not installed")
        return

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    # In production, register the compiled service:
    #   finrl_pb2_grpc.add_FinRLServiceServicer_to_server(FinRLServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("FinRL gRPC server started on port %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
