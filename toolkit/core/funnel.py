"""V4 Core — THE FUNNEL (unified T0→T3 × FORGE tiers).

Routes every work item to the lowest tier that can handle it.
Escalate only on uncertainty or irreversibility — never by default.
Every routing is appended to escalation-log.jsonl (single audit trail).

Merged from V2 escalation.py + FORGE auto-escalation rules.
Project-agnostic: no VIVIM terms in triggers.

Speed: routing is a pure function — no IO except the log append.
Budgets NEVER block (advisory only, per canon).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from . import common

# ---------------------------------------------------------------------------
# Tier names
# ---------------------------------------------------------------------------
# Funnel tiers
TIER_NAMES = {0: "T0-deterministic", 1: "T1-FLASH", 2: "T2-strong-LLM", 3: "T3-human"}
# FORGE tiers
FORGE_TIERS = {"FLASH", "CAPABLE", "STRONG", "CREATIVE"}

# Work kinds that are purely deterministic and NEVER escalate (speed-critical)
DETERMINISTIC_KINDS = {
    "hash-dedup", "parse", "topo-sort", "rollup", "survey",
    "status-rollup", "ke-cache-hit", "verbatim-gate-reject",
    "write", "dedup-check", "gate-check",
}


@dataclass
class WorkItem:
    kind: str
    src_id: str = ""
    confidence: float = 1.0        # 0..1 from deterministic/heuristic stage
    irreversible: bool = False
    novel_archetype: bool = False  # matches no known entity pack
    detail: str = ""
    # FORGE context (for auto-escalation rules)
    target_doc_status: str = ""    # RATIFIED etc.
    resolves_conflict: bool = False
    fan_in: int = 0
    retry_count: int = 0
    tags: list = field(default_factory=list)


@dataclass
class Route:
    tier: int                      # 0..3 funnel tier
    forge_tier: str = ""           # FLASH/CAPABLE/STRONG/CREATIVE (empty if T0)
    reason: str = ""
    blocking: bool = False
    esc_records: list = field(default_factory=list)

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]


class EscalationEngine:
    def __init__(self, cfg: dict):
        t = cfg.get("thresholds", {})
        self.t_auto = float(t.get("t_auto", 0.90))
        self.t_cheap = float(t.get("t_cheap", 0.60))
        self.t_llm = float(t.get("t_llm", 0.30))
        # Resolve data_dir for log
        dd = cfg.get("paths", {}).get("data_dir", "data")
        self.log_path = (common.V4_ROOT / dd).resolve() if not Path(dd).is_absolute() else Path(dd) / "escalation-log.jsonl"
        # Ensure parent exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Pure routing (no IO)
    # ------------------------------------------------------------------
    def route(self, w: WorkItem) -> Route:
        # 1) Pure-deterministic kinds never escalate.
        if w.kind in DETERMINISTIC_KINDS:
            return Route(0, "", "deterministic", False)

        # 2) Irreversibility ALWAYS gates to human, regardless of confidence.
        if w.irreversible:
            return Route(3, "STRONG", "irreversible operation", True)

        # 3) FORGE auto-escalation trampoline: bump FORGE tier before confidence ladder
        #    (these are advisory escalations — they raise the floor, not the funnel tier directly)
        forge_tier = self._forge_floor(w)

        # 4) Novelty with low confidence forces LLM classification.
        if w.novel_archetype and w.confidence < self.t_cheap:
            return Route(2, forge_tier or "CAPABLE", "novel archetype, low confidence", False)

        # 5) Confidence ladder.
        if w.confidence >= self.t_auto:
            return Route(0, forge_tier or "FLASH", "high confidence", False)
        if w.confidence >= self.t_cheap:
            return Route(1, forge_tier or "FLASH", "mid confidence", False)
        if w.confidence >= self.t_llm:
            return Route(2, forge_tier or "STRONG", "low confidence", False)

        # 6) Floor: too uncertain for any model -> human.
        return Route(3, forge_tier or "STRONG", "below LLM floor", True)

    def _forge_floor(self, w: WorkItem) -> str:
        """FORGE auto-escalation: compute minimum FORGE tier. Never de-escalates."""
        floors = []
        if w.target_doc_status == "RATIFIED":
            floors.append("STRONG")
        if w.resolves_conflict:
            floors.append("STRONG")
        if w.fan_in >= 5:
            floors.append("STRONG")
        if w.retry_count >= 2:
            floors.append("STRONG")
        if "ISG_SIGNOFF" in (w.tags or []):
            floors.append("STRONG")
        if not floors:
            return ""
        # Return highest floor
        order = {"FLASH": 0, "CAPABLE": 1, "STRONG": 2, "CREATIVE": 3}
        return max(floors, key=lambda x: order.get(x, 0))

    # ------------------------------------------------------------------
    # Dispatch (route + log)
    # ------------------------------------------------------------------
    def dispatch(self, w: WorkItem) -> Route:
        r = self.route(w)
        entry = {
            "ts": common.now_iso(),
            "src_id": w.src_id,
            "kind": w.kind,
            "confidence": round(w.confidence, 4),
            "tier": r.tier,
            "tier_name": r.tier_name,
            "forge_tier": r.forge_tier,
            "reason": r.reason,
            "blocking": r.blocking,
            "detail": w.detail,
        }
        common.append_jsonl(self.log_path, entry)
        if r.tier >= 2:
            common.log(f"escalate {w.src_id} {w.kind} -> {r.tier_name} ({r.reason})", "esc")
        return r

    def summary(self) -> dict:
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for e in common.read_jsonl(self.log_path):
            counts[e.get("tier", 0)] = counts.get(e.get("tier", 0), 0) + 1
        return counts
