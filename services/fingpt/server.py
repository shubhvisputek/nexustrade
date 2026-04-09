"""FinGPT gRPC stub server.

Returns mock sentiment scores for development and testing.
The real implementation would load a FinGPT sentiment model.
"""

from __future__ import annotations

import logging
import random
from concurrent import futures

logger = logging.getLogger(__name__)

try:
    import grpc

    _HAS_GRPC = True
except ImportError:
    _HAS_GRPC = False
    logger.warning("grpc not installed — FinGPT server will not start")


# ---------------------------------------------------------------------------
# Stub servicer (mock responses)
# ---------------------------------------------------------------------------

if _HAS_GRPC:

    class FinGPTServicer:
        """Mock FinGPT servicer that returns random sentiment scores."""

        def AnalyzeSentiment(self, request, context):  # noqa: N802
            """Return mock sentiment analysis.

            In production this would:
            1. Load the FinGPT model specified by request.model_name
            2. Tokenize each headline
            3. Run inference and return sentiment scores and labels
            """
            labels_pool = ["positive", "negative", "neutral"]
            scores = []
            labels = []

            for headline in request.headlines:
                score = random.uniform(-1.0, 1.0)
                scores.append(score)
                if score > 0.3:
                    labels.append("positive")
                elif score < -0.3:
                    labels.append("negative")
                else:
                    labels.append("neutral")

            logger.info(
                "FinGPT AnalyzeSentiment: %d headlines, model=%s",
                len(request.headlines),
                request.model_name or "fingpt_default",
            )

            response = type("SentimentResponse", (), {
                "scores": scores,
                "labels": labels,
            })()
            return response


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def serve(port: int = 50052) -> None:
    """Start the FinGPT gRPC server on the given port."""
    if not _HAS_GRPC:
        logger.error("Cannot start FinGPT server: grpc is not installed")
        return

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    # In production, register the compiled service:
    #   fingpt_pb2_grpc.add_FinGPTServiceServicer_to_server(FinGPTServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("FinGPT gRPC server started on port %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
