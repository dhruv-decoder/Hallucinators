"""Compliance evidence pack: turn the flight recorder into auditor-ready regulatory evidence.

Regulations differ by geography and industry and keep evolving, so nothing about a rule is hard-coded in the
detection logic -- governance lives in policy-as-config, and *evidence* is generated on demand from the
tamper-evident receipts. This module maps what ControlPlane already records (every decision, its per-axis
verdict, the human escalations, the hash chain) onto concrete controls in the **EU AI Act**, **ISO/IEC
42001**, and the **NIST AI RMF**, and renders a Markdown pack an auditor can read.

It is an *evidence aid*, not a certification: it shows, control by control, which recorded facts support the
requirement. The disclaimer to that effect is part of every generated pack.
"""

from controlplane.compliance.pack import generate_pack, render_markdown

__all__ = ["generate_pack", "render_markdown"]
