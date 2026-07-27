"""Mycelium Sentinel ingest service.

MQTT consumer for firmware event frames, on-host classifier (XGBoost primary,
1D-CNN comparison row per ADR-007), TimescaleDB sink, Grafana via compose.

Sprint 0.1 only ships the package skeleton. MQTT and storage land in Sprint 1.6,
the classifier in Sprint 2.2.
"""

__all__: list[str] = []
