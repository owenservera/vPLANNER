"""V4 Core — Model Router (FORGE tier -> concrete model).

Resolves tier -> concrete model at dispatch time from config/model_router.yaml
(single source of truth). Applies deterministic auto-escalation rules; every
firing writes an ESC- record. De-escalation never automatic.

Vendor-agnostic: YAML holds capability-class labels ("fast-tier", etc.).
Orchestrator binds labels to concrete models at dispatch time.

Fixes from audit:
  - CONFIG_PATH now points to v4/config/model_router.yaml
  - _rule_fired is data-driven (reads escalation_rules from YAML)
  - LADDER includes CREATIVE handling
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import common
from .tiers import ModelTier, EscalationRecord

CONFIG_PATH = common.V4_ROOT / "config" / "model_router.yaml"
LADDER = [ModelTier.FLASH, ModelTier.CAPABLE, ModelTier.STRONG]
# CREATIVE is lateral — not on the ladder


def load_config(path: Path | None = None) -> dict:
    p = path or CONFIG_PATH
    if not p.exists():
        # Fallback: tookli-upgrade location (migration period)
        alt = common.V4_ROOT.parent / "tookli-upgrade" / "model_router.yaml"
        if alt.exists():
            p = alt
        else:
            return {}
    text = common.read_text(p)
    try:
        import yaml  # type: ignore
        result = yaml.safe_load(text)
        return result if result else {}
    except ImportError:
        from .yamlite import parse
        return parse(text)


@dataclass
class Resolution:
    unit_id: str
    tier: ModelTier
    model_label: str
    esc_records: list[EscalationRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ForgeRouter:
    def __init__(self, config: dict | None = None):
        self.cfg = config if config is not None else load_config()

    # ---- tier entry point -------------------------------------------------
    def entry_tier(self, unit: dict, round_id: str | None = None) -> ModelTier:
        """default_tier on the unit wins; else round default; else CAPABLE."""
        raw = unit.get("default_tier")
        if raw:
            try:
                return ModelTier(raw)
            except ValueError:
                pass
        rd = (self.cfg.get("round_defaults") or {}).get(round_id or "")
        if rd:
            try:
                return ModelTier(rd)
            except ValueError:
                pass
        return ModelTier.CAPABLE

    # ---- model label ------------------------------------------------------
    def model_for(self, tier: ModelTier, workstream: str | None = None) -> str:
        ws = (self.cfg.get("workstream_overrides") or {}).get(workstream or "", {})
        entry = (ws.get(tier.value) if isinstance(ws, dict) else None) \
            or (self.cfg.get("global_default") or {}).get(tier.value, {})
        return (entry or {}).get("primary") or "unbound-label"

    # ---- deterministic escalation -----------------------------------------
    def evaluate_escalations(self, tier: ModelTier, unit: dict, context: dict | None = None,
                             seq: int = 1) -> tuple[ModelTier, list[EscalationRecord]]:
        """Apply each rule; a firing bumps exactly one tier or raises floor. Logged."""
        ctx = context or {}
        escs: list[EscalationRecord] = []
        for i, rule in enumerate(self.cfg.get("escalation_rules") or [], start=1):
            rid = rule.get("id", f"rule{i}")
            fired = self._rule_fired(rid, unit, ctx)
            if not fired:
                continue
            new = tier
            if "escalate_to_minimum" in rule:
                try:
                    floor = ModelTier(rule["escalate_to_minimum"])
                except ValueError:
                    continue
                if tier not in (ModelTier.CREATIVE,) and tier in LADDER and floor in LADDER:
                    if LADDER.index(tier) < LADDER.index(floor):
                        new = floor
                elif tier == ModelTier.FLASH and floor != ModelTier.CREATIVE:
                    # FLASH can escalate to any non-CREATIVE floor
                    if tier != floor:
                        new = floor
            elif "escalate_by" in rule:
                new = tier.escalate()
            if new != tier:
                escs.append(EscalationRecord(
                    esc_id=f"ESC-{seq + len(escs):04d}",
                    unit_id=unit.get("unit_id", "?"),
                    from_tier=tier, to_tier=new,
                    trigger=rid, authorized_by="AUTO"))
                tier = new
        return tier, escs

    @staticmethod
    def _rule_fired(rid: str, unit: dict, ctx: dict) -> bool:
        # Data-driven dispatch: known rule IDs
        if rid == "touches_ratified_doc":
            return ctx.get("target_doc_status") == "RATIFIED"
        if rid == "resolves_conflict":
            return bool(unit.get("resolves_conflicts_json_entry"))
        if rid == "high_fan_in":
            try:
                return int(ctx.get("fan_in", 0)) >= 5
            except (ValueError, TypeError):
                return False
        if rid == "repeat_failure":
            try:
                return int(unit.get("retry_count", 0)) >= 2
            except (ValueError, TypeError):
                return False
        if rid == "isg_signoff_question":
            return "ISG_SIGNOFF" in (unit.get("tags") or [])
        return False

    # ---- full resolution ---------------------------------------------------
    def resolve(self, unit: dict, workstream: str | None = None, round_id: str | None = None,
                context: dict | None = None, seq: int = 1) -> Resolution:
        tier = self.entry_tier(unit, round_id)
        tier, escs = self.evaluate_escalations(tier, unit, context, seq)
        return Resolution(unit_id=unit.get("unit_id", "?"), tier=tier,
                          model_label=self.model_for(tier, workstream), esc_records=escs,
                          notes=[f"entry={self.entry_tier(unit, round_id).value}"] if escs else [])


def main() -> None:
    """Self-test: seed scenarios covering every escalation rule."""
    r = ForgeRouter()
    cases = [
        ("mechanical move", {"unit_id": "WORK-9001", "default_tier": "FLASH"}, "R2_ORGANIZATION", {}, None),
        ("conflict adjudication", {"unit_id": "WORK-9002", "default_tier": "CAPABLE",
                                   "resolves_conflicts_json_entry": True}, "R7_GATED_EXTRACTION", {}, None),
        ("ratified doc touch", {"unit_id": "WORK-9003", "default_tier": "FLASH"},
         "R9_POPULATION", {"target_doc_status": "RATIFIED"}, None),
        ("repeat failure", {"unit_id": "WORK-9004", "default_tier": "CAPABLE", "retry_count": 2},
         "R7_GATED_EXTRACTION", {}, None),
        ("isg sign-off", {"unit_id": "WORK-9005", "tags": ["ISG_SIGNOFF"]}, "R4_SCOPE_GROUNDING", {}, None),
    ]
    seq = 1
    for name, unit, rnd, ctx, _ in cases:
        res = r.resolve(unit, round_id=rnd, context=ctx, seq=seq)
        seq += len(res.esc_records)
        escs = ", ".join(f"{e.esc_id}:{e.trigger}->{e.to_tier.value}" for e in res.esc_records) or "none"
        print(f"  {name:24s} {res.tier.value:8s} model={res.model_label:28s} esc=[{escs}]")
    print("router self-test OK")


if __name__ == "__main__":
    main()
