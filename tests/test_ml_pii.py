"""Tests for the model-backed Presidio PII detector.

Skipped automatically when the optional [ml] extra or the spaCy model is not installed, so the core test
suite stays runnable without heavy dependencies.
"""

from __future__ import annotations

import pytest

from controlplane.core.types import RequestContext


def _detector_or_skip():
    presidio = pytest.importorskip("presidio_analyzer")  # noqa: F841
    from controlplane.cascade.detectors.responsibility_ml import PresidioPiiDetector, _get_analyzer

    try:
        _get_analyzer()
    except Exception as exc:  # spaCy model not downloaded, etc.
        pytest.skip(f"Presidio/spaCy not fully available: {exc}")
    return PresidioPiiDetector()


def test_presidio_catches_freetext_pii_the_regex_misses():
    from controlplane.cascade.detectors import RegexPiiDetector

    ctx = RequestContext(
        request_id="t",
        response="The complaint was filed by Sarah Chen, who lives in Mumbai.",
    )
    # The regex detector is blind to names and locations.
    assert RegexPiiDetector().run(ctx).score == 0.0

    # The NER detector flags them.
    signal = _detector_or_skip().run(ctx)
    assert signal.score > 0.4
    assert "PERSON" in signal.detail["entities"]


def test_presidio_stays_quiet_on_clean_text():
    ctx = RequestContext(request_id="t", response="Support is available 9am to 6pm on weekdays.")
    signal = _detector_or_skip().run(ctx)
    assert signal.score < 0.4
