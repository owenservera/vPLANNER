"""V4 Core — Model Tier primitive.

Vendor-agnostic capability tiers. Tier -> concrete model resolution happens in
core/router.py via config/model_router.yaml. See TOOLKIT-V2/V3-MAXIMAL-UPGRADE-DESIGN.md.

This module is project-agnostic: no VIVIM terms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ModelTier(str, Enum):
    """Four-tier capability primitive. CREATIVE is lateral, not above STRONG."""
    FLASH = "FLASH"
    CAPABLE = "CAPABLE"
    STRONG = "STRONG"
    CREATIVE = "CREATIVE"

    @property
    def description(self) -> str:
        return {
            ModelTier.FLASH: "High-volume, low-ambiguity, mechanical transforms.",
            ModelTier.CAPABLE: "Standard implementation work with a clear spec.",
            ModelTier.STRONG: "Judgment-heavy or cross-cutting work; adjudication; ratification.",
            ModelTier.CREATIVE: "Open-ended generation with no single correct answer.",
        }[self]

    def escalate(self) -> "ModelTier":
        """One-tier escalation. CREATIVE is lateral — ceilings at STRONG."""
        ladder = {
            ModelTier.FLASH: ModelTier.CAPABLE,
            ModelTier.CAPABLE: ModelTier.STRONG,
            ModelTier.STRONG: ModelTier.STRONG,       # ceiling
            ModelTier.CREATIVE: ModelTier.CREATIVE,   # lateral-max
        }
        return ladder[self]


@dataclass
class StageTier:
    """A single stage of a multi-stage unit, with its own tier."""
    stage: str
    tier: ModelTier


@dataclass
class EscalationRecord:
    """Auditable record of a tier escalation. Every auto-escalation MUST produce one."""
    esc_id: str
    unit_id: str
    from_tier: ModelTier
    to_tier: ModelTier
    trigger: str
    authorized_by: str = "AUTO"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "esc_id": self.esc_id,
            "unit_id": self.unit_id,
            "from_tier": self.from_tier.value,
            "to_tier": self.to_tier.value,
            "trigger": self.trigger,
            "authorized_by": self.authorized_by,
            "timestamp": self.timestamp,
        }


# NOTE: cost multipliers are NOT hardcoded here — they live in config/model_router.yaml
# (global_default). This dict is only for quick local estimation when router is unavailable.
DEFAULT_COST_MULTIPLIER_FALLBACK = {
    ModelTier.FLASH: 1,
    ModelTier.CAPABLE: 4,
    ModelTier.STRONG: 15,
    ModelTier.CREATIVE: 15,
}


def estimate_relative_cost(tier: ModelTier, base_tokens: int) -> int:
    """Rough relative-cost estimate in FLASH-equivalent token units."""
    return base_tokens * DEFAULT_COST_MULTIPLIER_FALLBACK[tier]
