"""V4 Adapter — Archives (.zip/.tar/.gz) → DEFERRED.

Project-agnostic: archives are never extracted during survey.
They are marked DEFERRED-EXTRACT and require explicit unpacking.
"""
from __future__ import annotations

# No code — archives are handled in t0_survey.py via extension check.
# This module exists as a named adapter for the routing table.
ADAPTER_KIND = "archive"
