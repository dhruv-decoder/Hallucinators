"""Detectors: cheap heuristics (T0) today, with a documented upgrade path to heavier models (T1/T2).

Each detector belongs to one axis and one tier and implements a single ``run`` method. Nothing here
fabricates a result: a detector that cannot assess a request (for example, a groundedness detector with
no retrieved context) abstains by returning a low-confidence signal and says so in ``detail``.
"""

from controlplane.cascade.detectors.base import CostDetector, Detector
from controlplane.cascade.detectors.cost import ModelOverkillDetector, SemanticCacheDetector
from controlplane.cascade.detectors.performance import (
    GroundednessHeuristicDetector,
    OverconfidenceDetector,
    SelfConsistencyDetector,
)
from controlplane.cascade.detectors.responsibility import RegexPiiDetector

__all__ = [
    "Detector",
    "CostDetector",
    "RegexPiiDetector",
    "GroundednessHeuristicDetector",
    "OverconfidenceDetector",
    "SelfConsistencyDetector",
    "ModelOverkillDetector",
    "SemanticCacheDetector",
]
