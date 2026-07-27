"""Smoke test for the ingest package.

Real ingest tests land in Sprint 1.6 (MQTT round-trip) and Sprint 2.2
(classifier). This test only asserts the package imports.
"""

import ingest


def test_ingest_imports() -> None:
    assert hasattr(ingest, "__all__")
