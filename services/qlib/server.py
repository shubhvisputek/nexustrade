"""Qlib gRPC stub server.

Returns mock alpha factors for development and testing.
The real implementation would use Microsoft Qlib for factor computation.
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
    logger.warning("grpc not installed — Qlib server will not start")


# ---------------------------------------------------------------------------
# Stub servicer (mock responses)
# ---------------------------------------------------------------------------

if _HAS_GRPC:

    class QlibServicer:
        """Mock Qlib servicer that returns random factor values."""

        # Default factor names returned by the stub
        DEFAULT_FACTORS = [
            "alpha001", "alpha002", "alpha003",
            "momentum_20d", "volatility_60d",
            "mean_reversion_5d", "volume_surprise",
        ]

        def ComputeFactors(self, request, context):  # noqa: N802
            """Return mock alpha factors.

            In production this would:
            1. Initialize Qlib with the requested date range
            2. Compute the factor_set for the given symbol
            3. Return a map of factor name -> float value
            """
            factors = {}
            for factor_name in self.DEFAULT_FACTORS:
                factors[factor_name] = random.uniform(-1.0, 1.0)

            logger.info(
                "Qlib ComputeFactors: symbol=%s range=%s..%s factor_set=%s",
                request.symbol,
                request.start_date,
                request.end_date,
                request.factor_set or "default",
            )

            response = type("FactorResponse", (), {
                "factors": factors,
            })()
            return response


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def serve(port: int = 50053) -> None:
    """Start the Qlib gRPC server on the given port."""
    if not _HAS_GRPC:
        logger.error("Cannot start Qlib server: grpc is not installed")
        return

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    # In production, register the compiled service:
    #   qlib_pb2_grpc.add_QlibServiceServicer_to_server(QlibServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("Qlib gRPC server started on port %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
