#!/usr/bin/env python3
"""V4 Serve — Control Center V4 MAX. Fully wired, project-agnostic, massive upgrade.

Single-file HTML, derived-only, CC_DATA island. No server, no deps, file://.
Wires ALL 14 data sources. Features:
  - L0 Scope Constitution (ledger × ke × disposition × category, fully filterable)
  - Fragment Inspector (click any row → verbatim + anchor + sha)
  - Entity Graph, Dependency Graph, Traceability (SVG, no library)
  - Gate Matrix G1-G8 (advisory G6 never blocks)
  - Funnel Timeline + Tier Distribution (from escalation-log.jsonl)
  - Budget burn-down (unconstrained-aware)
  - Unified Search (Ctrl+K palette)
  - Inline Adjudication (conflict/mixed rows)
  - Watch polling (meta refresh fallback)
  - Audit snapshots + applied diff + deep links
  - Decision Queue (8 types, batch mixed-batch, export round-trip)

Project-agnostic: no VIVIM terms, categories/phases/workstreams derived from data.
Corruption-hardened: every data load has fallback, never crashes on missing file.
Speed: budgets unconstrained by default — never gate.
"""
from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

E = html.escape

# Colors (ink/evidence-bench)
C_EXTRACT, C_SKIP, C_REF, C_PARK, C_UNRULED = "#6e8f5c", "#b0523a", "#6f8fae", "#c8963f", "#c8963f"
C_DONE, C_WIP, C_WAIT, C_INFO, C_DIM = "#6e8f5c", "#c8963f", "#9a8f78", "#6f8fae", "#9a8f78"
DISP_COLOR = {"EXTRACT": C_EXTRACT, "SKIP": C_SKIP, "REF-ONLY": C_REF, "PARKED": C_PARK, "UNRULED": C_UNRULED}
LIFE_COLOR = {"EMPTY": C_DIM, "NAIVE": C_WIP, "RATIFIED": C_DONE}
STATUS_COLOR = {"PENDING": C_DIM, "IN_PROGRESS": C_WIP, "DONE": C_DONE, "SKIPPED-EXACT-DUP": C_INFO,
                "DEFERRED-EXTRACT": C_WIP, "DEFERRED-CODE-TRACK": C_WIP, "FAILED": C_SKIP, "HOLDING-MIXED": C_WIP}
TIER_COLOR = {0: C_DIM, 1: C_EXTRACT, 2: C_INFO, 3: C_SKIP}
FORGE_COLOR = {"FLASH": C_DIM, "CAPABLE": C_EXTRACT, "STRONG": C_INFO, "CREATIVE": C_PARK}

KE_OPTIONS = ["KERNEL", "IN-SCOPE-REF", "MIXED", "OUT-OF-SCOPE-CANDIDATE", "CLEAN"]
DISP_OPTIONS = ["EXTRACT", "SKIP", "REF-ONLY", "PARKED"]


def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_progressive_state(data_dir: Path) -> dict:
    """Replay control-center-state/rounds/round-NNN.json in order.
    Returns {unlocked: set[M*], latest: dict[module->{round doc}], errors: [{path, error}], rounds: [docs]}.
    If rounds/ is empty, returns unlocked={'M0','M1','M2','M3','M4','M5'} fallback so CC renders without progressive history (cold start)."""
    rounds_dir = data_dir.parent / "control-center-state" / "rounds"
    # Also try toolkit/control-center-state/rounds/ if data_dir is toolkit/data
    alt = common.V4_ROOT / "control-center-state" / "rounds"
    for cand in [rounds_dir, alt]:
        if cand.exists() and any(cand.glob("round-*.json")):
            rounds_dir = cand
            break
    if not rounds_dir.exists():
        return {"unlocked": {"M0", "M1", "M2", "M3", "M4", "M5"}, "latest": {}, "errors": [], "rounds": [], "is_progressive": False}
    docs: list[dict] = []
    errors: list[dict] = []
    for p in sorted(rounds_dir.glob("round-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            docs.append(d)
        except Exception as e:
            errors.append({"path": str(p), "error": str(e)})
    if not docs and not errors:
        return {"unlocked": {"M0", "M1", "M2", "M3", "M4", "M5"}, "latest": {}, "errors": [], "rounds": [], "is_progressive": False}
    unlocked: set[str] = set()
    latest: dict[str, dict] = {}
    for d in sorted(docs, key=lambda x: x.get("round", 0)):
        for m in d.get("modules_unlocked", []):
            unlocked.add(m)
            latest[m] = d
    return {"unlocked": unlocked, "latest": latest, "errors": errors, "rounds": docs, "is_progressive": True}

def pill(text, color):
    return f'<span class="pill" style="background:{color}26;color:{color}">{E(str(text))}</span>'

def donut(segs, center_top, center_sub):
    total = sum(v for _, v, _ in segs) or 1
    off = 25.0
    arcs = []
    for label, val, color in segs:
        frac = val / total
        arcs.append(f'<circle r="15.915" cx="21" cy="21" fill="none" stroke="{color}" stroke-width="5"'
                    f' stroke-dasharray="{frac*100:.2f} {100-frac*100:.2f}" stroke-dashoffset="{off:.2f}"></circle>')
        off = (off - frac * 100) % 100
    legend = "".join(f'<div class="lg"><span class="dot" style="background:{c}"></span>{E(l)} <b>{v}</b></div>' for l, v, c in segs)
    return (f'<div class="donutwrap"><svg viewBox="0 0 42 42" class="donut">{"".join(arcs)}'
            f'<text x="21" y="21.5" class="dtop">{E(center_top)}</text><text x="21" y="26" class="dsub">{E(center_sub)}</text></svg>'
            f'<div class="lgcol">{legend}</div></div>')

def build_queue(rows, ke_cache, scope_model, conflicts, dup_ledger, budgets, esc_log, discovered_clusters=None):
    """Build queue — 9 types including discovered-cluster (blind start). Project-agnostic."""
    items = []
    # 0. discovered-cluster — PARKED clusters awaiting ruling (blind start headline)
    if discovered_clusters:
        for c in discovered_clusters:
            cid = c.get("id", "")
            items.append({"id": "DISC::" + cid, "type": "discovered-cluster", "target": cid,
                           "title": f"Rule discovered cluster {cid}: {c.get('name','')[:40]}",
                           "subject": f"{len(c.get('member_paths',[]))} files — keywords: {', '.join(c.get('keywords',[])[:4])}",
                           "evidence": {"path": "; ".join(c.get('evidence', [])[:1]), "hits": f"{len(c.get('member_paths',[]))} files — disposition: {c.get('disposition','PARKED')}"},
                           "options": DISP_OPTIONS, "priority": 0})
    # Need ke_map for display
    ke_map = {}
    for r in rows:
        if r.get("ke_class"):
            ke_map[r["path"]] = r["ke_class"]

    # 1. ke-class NEEDS-REVIEW / MIXED without ruling (from tracker) — opt-in
    for r in rows:
        kc = r.get("ke_class", "")
        if kc in ("NEEDS-REVIEW",) and r.get("status") not in ("SKIPPED-EXACT-DUP", "FAILED"):
            items.append({"id": "KE::" + r["path"], "type": "ke-class", "target": r["path"],
                           "title": "Rule KE class", "subject": r["path"][:90],
                           "evidence": {"path": r["path"], "hits": kc},
                           "options": KE_OPTIONS, "priority": 2})
    # 2. disposition UNRULED
    for r in rows:
        if (r.get("scope_disposition") is None or r.get("scope_disposition") == "UNRULED") and r["status"] not in ("SKIPPED-EXACT-DUP", "FAILED"):
            if r.get("scope_disposition") is None:
                items.append({"id": "UNRULED::" + r["path"], "type": "disposition", "target": r["path"],
                               "title": "Rule file disposition", "subject": r["path"],
                               "evidence": {"path": r["path"], "hits": f"{r['category']} / {r['source_type']} / {r['bytes']} bytes"},
                               "options": DISP_OPTIONS, "priority": 1})
    # 3. mixed-batch (ONE item for all HOLDING-MIXED)
    holding = [r for r in rows if r.get("status") == "HOLDING-MIXED"]
    if holding:
        items.append({"id": "MIXED::BATCH", "type": "mixed-batch", "target": "HOLDING-MIXED",
                       "title": f"Batch ruling: {len(holding)} MIXED files", "subject": f"{len(holding)} files held — one ruling covers all",
                       "evidence": {"path": ", ".join(r["path"][:40] for r in holding[:3]), "hits": f"{len(holding)} files"},
                       "options": ["split-extract", "extract-all", "skip-all", "hold-all"], "priority": 0})

    # 4. interview questions (from scope model)
    answered = set()
    dd = None
    # Try to find interview answers
    import pathlib
    for p in Path(common.V4_ROOT / "data" / "scope").glob("interview-answers-v*.json"):
        d = load_json(p, {}) or {}
        for a in d.get("answers", []):
            answered.add(a.get("question_id") or a.get("id"))
    for q in (scope_model.get("open_questions", []) if isinstance(scope_model, dict) else []):
        if q.get("id") not in answered:
            items.append({"id": "IQ::" + q.get("id", ""), "type": "interview", "target": q.get("id", ""),
                           "title": "Interview question", "subject": q.get("question", "")[:120],
                           "evidence": {"path": "scope/model open_questions", "hits": q.get("id", "")},
                           "options": ["approve", "needs-changes", "unsure"], "free": True, "priority": 3})

    # 5. conflicts
    if isinstance(conflicts, dict):
        conflicts_list = conflicts.get("open", [])
    elif isinstance(conflicts, list):
        conflicts_list = conflicts
    else:
        conflicts_list = []
    for c in conflicts_list:
        if isinstance(c, dict) and c.get("status") == "UNRESOLVED":
            cid = c.get("conflict_id", c.get("id", str(len(items))))
            items.append({"id": "CFL::" + str(cid), "type": "conflict", "target": str(cid),
                           "title": "Conflict ruling", "subject": str(c.get("entity_key", c.get("entity", cid)))[:90],
                           "evidence": {"path": ", ".join(c.get("sources", [])[:3]), "hits": f"{c.get('versions',2)} versions"},
                           "options": ["side-A", "side-B", "merge", "defer"], "priority": 0})

    # 6. alias dup-ledger
    dup_list = dup_ledger if isinstance(dup_ledger, list) else (dup_ledger.get("entries", []) if isinstance(dup_ledger, dict) else [])
    for d in dup_list if isinstance(dup_list, list) else []:
        if isinstance(d, dict) and d.get("type") == "alias-merge-candidate" and not d.get("resolution"):
            items.append({"id": "ALIAS::" + str(d.get("id", len(items))), "type": "alias", "target": str(d.get("id", "")),
                           "title": "Alias merge candidate", "subject": str(d.get("entity", ""))[:90],
                           "evidence": {"path": str(d.get("sources", ""))[:140], "hits": ""},
                           "options": ["merge", "keep-distinct"], "priority": 2})

    # 7. budget breach (advisory — only if budgets configured and over threshold)
    if isinstance(budgets, list):
        for b in budgets:
            if not isinstance(b, dict):
                continue
            if b.get("bud_id") == "BUD-UNCONSTRAINED":
                continue
            est = b.get("est_tokens_total", b.get("est_tokens", 0))
            actual = b.get("actual_tokens_spent", b.get("actual_tokens", 0))
            thresh = b.get("alert_threshold_pct", 80)
            if est > 0 and actual > est * thresh / 100:
                items.append({"id": "BUD::" + b["bud_id"], "type": "budget-breach", "target": b["bud_id"],
                               "title": "Budget advisory", "subject": f"{b['bud_id']} {actual}/{est} ({actual/est*100:.0f}%) over {thresh}%",
                               "evidence": {"path": b["bud_id"], "hits": f"{actual}/{est}"},
                               "options": ["acknowledge", "re-budget"], "priority": 4})

    # 8. escalation review (low confidence T2)
    if isinstance(esc_log, list):
        for e in esc_log:
            if isinstance(e, dict) and e.get("tier") == 2 and e.get("confidence", 1) < 0.5:
                # One per low-conf escalation
                items.append({"id": "ESC::" + e.get("src_id","") + "::" + e.get("kind",""), "type": "escalation-review",
                               "target": e.get("src_id",""), "title": "Escalation review",
                               "subject": f"{e.get('kind','')} low confidence {e.get('confidence','')}",
                               "evidence": {"path": e.get("src_id",""), "hits": e.get("reason","")},
                               "options": ["confirm", "escalate", "de-escalate"], "priority": 5})
                if len([x for x in items if x["type"] == "escalation-review"]) >= 5:
                    break  # cap at 5

    # Sort by priority (0 highest)
    items.sort(key=lambda x: x.get("priority", 9))
    return items


def _resolve_data_dir(cfg: dict) -> Path:
    dd = Path(cfg["paths"]["data_dir"])
    return (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="publish snapshot to history/")
    args = ap.parse_args()
    cfg = tomlite.load()
    run(cfg, publish=args.publish)

def card(inner):
    return f"<div class='card'>{inner}</div>"

def stacked(label, segs, total):
    if total <= 0:
        return ""
    inner = "".join(f"<div style=\"width:{v/total*100:.1f}%;background:{c}\" title=\"{E(l)}: {v}\"></div>" for l, v, c in segs if v > 0)
    return f"<div class='sbar'><div class='slabel dim'>{E(label)} ({total})</div><div class='strack'>{inner}</div></div>"


# ── CSS (ink/evidence-bench + V4 MAX additions: inspector, graphs, gate matrix, palette) ──
CSS = """
:root{--ink-0:#15130f;--ink-1:#1d1a15;--ink-2:#26221b;--hair:#3a352a;--paper:#e8e2d3;--dim:#9a8f78;
--amber:#c8963f;--moss:#6e8f5c;--brick:#b0523a;--slate:#6f8fae}
*{box-sizing:border-box}
body{margin:0;background:var(--ink-0);color:var(--paper);font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:13px}
a{color:var(--slate);text-decoration:none}a:hover{text-decoration:underline}
code,.mono{font-family:ui-monospace,'Cascadia Mono',Consolas,monospace}
:focus-visible{outline:2px solid var(--slate);outline-offset:1px}
.muted{color:var(--dim);font-size:12px}.dim{color:var(--dim);font-size:12px}
.vtag{font-size:10px;background:var(--moss);color:var(--ink-0);padding:1px 6px;border-radius:4px;vertical-align:middle}
.desk{display:grid;grid-template-columns:190px minmax(0,1fr) 340px;min-height:100vh}
.rail{position:sticky;top:0;height:100vh;overflow:auto;background:var(--ink-1);border-right:1px solid var(--hair);padding:16px 12px}
.rail-h{font-size:11px;color:var(--dim);margin:0 0 8px 2px}
.rrow{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;color:var(--paper);font-size:12px;border:none;background:none;width:100%;text-align:left;cursor:default}
button.rrow{cursor:pointer}button.rrow:hover{background:var(--ink-2)}
.dot{width:8px;height:8px;border-radius:50%;border:1px solid var(--hair);flex:none}
.dot.done{background:var(--moss);border-color:var(--moss)}.dot.wip{background:var(--amber);border-color:var(--amber)}
.lbtn.on{background:var(--ink-2)}
.railfoot{margin-top:22px;font-size:12px}
.canvas{padding:20px 26px 60px;min-width:0}
.chead-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
h1{font-size:24px;font-weight:650;margin:0 0 2px}
.sub{color:var(--dim);font-size:12px;margin-top:4px}
h2{font-size:15px;font-weight:650;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--hair)}
.hsub{color:var(--dim);font-weight:400;font-size:12px;margin-left:8px}
.krow{display:flex;gap:26px;flex-wrap:wrap;margin-top:14px}
.kpi{background:none;border:none;border-bottom:2px solid var(--hair);padding:2px 2px 6px;cursor:pointer;text-align:left;color:var(--paper)}
.kpi:hover{background:var(--ink-1)}
.knum{display:block;font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.klbl{font-size:12px;color:var(--dim)}
.chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.chip{background:var(--ink-1);border:1px solid var(--hair);border-radius:12px;color:var(--paper);padding:3px 11px;font-size:12px;cursor:pointer}
.chip:hover{border-color:var(--slate)}.chip.sel{background:var(--ink-2);border-color:var(--slate)}
.search{background:var(--ink-1);border:1px solid var(--hair);color:var(--paper);border-radius:6px;padding:5px 10px;font-size:12px;min-width:240px}
.search-btn{background:var(--ink-1);border:1px solid var(--hair);color:var(--dim);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;margin-left:6px}
.search-btn:hover{border-color:var(--slate);color:var(--paper)}
.tblwrap{max-height:540px;overflow:auto;border:1px solid var(--hair);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{position:sticky;top:0;background:var(--ink-1);color:var(--dim);text-align:left;padding:6px 9px;font-weight:500;border-bottom:1px solid var(--hair)}
td{padding:4px 9px;border-bottom:1px solid var(--hair);color:var(--paper)}
tr:hover td{background:var(--ink-1)}
tr.q-linked{cursor:pointer}tr.q-linked td:first-child{box-shadow:inset 2px 0 0 var(--amber)}
.crow{cursor:pointer}
.crow.has-frags{border-left:2px solid var(--moss)}
.num{text-align:right}.mono{font-size:11px;color:#c9c0ac}
.pill{border-radius:9px;padding:1px 8px;font-size:11px;display:inline-block;font-weight:500}
.tl{border-left:1px solid var(--hair);margin-left:6px;padding-left:16px;display:grid;gap:12px;max-width:860px}
.tli{display:flex;gap:10px}.tldot{width:9px;height:9px;border-radius:50%;margin-top:5px;flex:none}
.tls{font-size:13px}.tlbody{max-width:80ch}
.card{background:var(--ink-1);border:1px solid var(--hair);border-radius:8px;padding:13px 15px;font-size:12px}
.grid{display:grid;gap:10px;margin-top:10px}
.g2{grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}.g3{grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.stmt{max-width:80ch;line-height:1.55;font-size:13px}
.stg{margin:6px 0}.sm{margin:4px 0;color:#c9c0ac}.empty{display:flex;gap:8px;align-items:flex-start;max-width:70ch;line-height:1.5}
.donutwrap{display:flex;gap:14px;align-items:center}.donut{width:150px;flex:none}
.dtop{fill:var(--paper);font-size:8px;font-weight:700;text-anchor:middle;font-family:ui-monospace,monospace}
.dsub{fill:var(--dim);font-size:3.4px;text-anchor:middle}
.lgcol{display:grid;gap:4px}.lg{font-size:12px;color:var(--paper)}.lg .dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
.sbar{margin:7px 0}.slabel{margin-bottom:3px}.strack{display:flex;height:9px;border-radius:4px;overflow:hidden;background:var(--ink-2)}
.queue{position:sticky;top:0;height:100vh;overflow:auto;background:var(--ink-1);border-left:1px solid var(--hair);display:flex;flex-direction:column}
.qhead{display:flex;align-items:center;gap:8px;padding:14px 14px 10px;font-weight:650;border-bottom:1px solid var(--hair)}
.qclose{margin-left:auto;background:none;border:1px solid var(--hair);color:var(--dim);border-radius:6px;width:24px;height:24px;cursor:pointer}
.qitems{flex:1;overflow:auto;padding:12px;display:grid;gap:10px;align-content:start}
.qitem{background:var(--ink-0);border:1px solid var(--hair);border-radius:8px;padding:11px 12px}
.qitem .qt{font-size:11px;color:var(--amber);margin-bottom:4px}
.qitem .qs{font-size:12px;margin-bottom:6px;max-width:60ch;word-break:break-word}
.qitem .qe{font-family:ui-monospace,Consolas,monospace;font-size:10px;color:var(--dim);margin-bottom:8px;word-break:break-all}
.qopts{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.qopt{background:var(--ink-2);border:1px solid var(--hair);color:var(--paper);border-radius:6px;padding:3px 10px;font-size:11px;cursor:pointer}
.qopt:hover{border-color:var(--slate)}
.qopt.picked{border-color:var(--moss);color:var(--moss)}
.qnote{width:100%;background:var(--ink-2);border:1px solid var(--hair);color:var(--paper);border-radius:6px;padding:4px 8px;font-size:11px;margin-bottom:7px}
.qresolve{background:none;border:1px solid var(--moss);color:var(--moss);border-radius:6px;padding:3px 12px;font-size:11px;cursor:pointer}
.qresolve:hover{background:rgba(110,143,92,.12)}
.qitem.resolved{border-color:rgba(110,143,92,.4)}
.qitem.resolved .qt{color:var(--moss)}
.qitem.resolving{transform:translateX(-60px);opacity:0;transition:transform .35s ease,opacity .35s ease}
.qfoot{border-top:1px solid var(--hair);padding:12px;display:grid;gap:8px}
.btn{border:1px solid var(--hair);background:var(--ink-2);color:var(--paper);border-radius:6px;padding:7px 12px;font-size:12px;cursor:pointer}
.btn.primary{border-color:var(--slate);color:var(--slate)}
.btn.sm{padding:4px 10px;font-size:11px}
.btn:hover{border-color:var(--slate)}
.qtoggle{display:none;background:var(--ink-2);border:1px solid var(--hair);color:var(--paper);border-radius:12px;padding:2px 10px;font-size:11px;cursor:pointer;margin-left:6px}
.qbadge{color:var(--amber)}
.foot{margin-top:40px;border-top:1px solid var(--hair);padding-top:14px}
.loopdim{font-size:12px;color:var(--paper);max-width:90ch;margin-bottom:6px}
/* V4 MAX additions */
.inspector{margin-top:12px;background:var(--ink-1);border:1px solid var(--moss);border-radius:8px;padding:12px}
.insp-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.insp-body{max-height:400px;overflow:auto}
.frag-card{background:var(--ink-0);border:1px solid var(--hair);border-radius:6px;padding:8px 10px;margin-bottom:8px}
.frag-card .fk{font-size:11px;color:var(--amber)}
.frag-card .fv{font-family:ui-monospace,monospace;font-size:11px;white-space:pre-wrap;word-break:break-word;background:var(--ink-2);padding:6px;border-radius:4px;margin-top:4px}
.graph-box{height:280px;border:1px solid var(--hair);border-radius:6px;background:var(--ink-0);margin-top:8px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.gate-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-top:8px}
.gate-cell{border:1px solid var(--hair);border-radius:6px;padding:8px;border-left:3px solid var(--hair)}
.gate-cell.pass{border-left-color:var(--moss)}.gate-cell.fail{border-left-color:var(--brick)}
.budget-bars{margin-top:8px;display:grid;gap:6px}
.brow{display:flex;align-items:center;gap:8px;font-size:11px}
.btrack{flex:1;height:10px;background:var(--ink-2);border-radius:5px;overflow:hidden;min-width:120px}
.bfill{height:100%;border-radius:5px;transition:width .3s}
.timeline{margin-top:8px;display:grid;gap:4px;max-height:320px;overflow:auto}
.tlane{font-size:11px;padding:2px 6px;border-radius:4px;background:var(--ink-0);border:1px solid var(--hair)}
.palette{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding-top:10vh;z-index:100}
.pal-box{background:var(--ink-1);border:1px solid var(--hair);border-radius:10px;width:min(560px,90vw);max-height:60vh;display:flex;flex-direction:column;overflow:hidden}
.pal-input{background:var(--ink-0);border:none;border-bottom:1px solid var(--hair);color:var(--paper);padding:12px 14px;font-size:14px;width:100%;outline:none}
.pal-results{overflow:auto;max-height:40vh}
.pal-item{padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--hair);font-size:12px}
.pal-item:hover,.pal-item.sel{background:var(--ink-2)}
.fb-panel{margin-top:10px;border:1px solid var(--hair);border-radius:8px;padding:10px;background:var(--ink-0)}
.fb-head{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600}
.fb-textarea{width:100%;min-height:60px;background:var(--ink-1);border:1px solid var(--hair);color:var(--paper);border-radius:6px;padding:6px 8px;font-size:12px;margin-top:6px}
.fb-row{display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap}
.fb-badge{background:var(--amber);color:var(--ink-0);padding:1px 6px;border-radius:9px;font-size:11px}
@media (max-width:1100px){
  .desk{grid-template-columns:56px minmax(0,1fr) 0}
  .rlbl,.rail-h,.railfoot{display:none}
  .rrow{justify-content:center;padding:7px 0}
  .queue{position:fixed;top:0;right:0;bottom:0;width:min(360px,92vw);transform:translateX(105%);transition:transform .25s ease;z-index:50;box-shadow:-12px 0 30px rgba(0,0,0,.45)}
  body.queue-open .queue{transform:none}
  .qtoggle{display:inline-block}
}
@media (max-width:700px){
  .desk{display:block}
  .rail{position:static;height:auto;display:flex;gap:4px;overflow-x:auto;border-right:none;border-bottom:1px solid var(--hair);padding:8px}
  .railfoot{display:none}
  .queue{top:auto;height:auto;max-height:62vh;width:100%;transform:translateY(105%);border-left:none;border-top:1px solid var(--hair)}
  body.queue-open .queue{transform:none}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

# ── JS (V4 MAX — queue + inspector + palette + graphs + watch) ──
JS = """
const Q = CC_DATA.queue || [];
const FRAGS = CC_DATA.fragments_sample || [];
const BOX2ID = {};
const IS_SNAPSHOT = /\\/history\\//.test(location.pathname);
let resolutions = {};
let picked = {};

// Fragment lookup by src_id
const FRAG_BY_SRC = {};
for(const f of FRAGS){ (FRAG_BY_SRC[f.src_id] = FRAG_BY_SRC[f.src_id] || []).push(f); }

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function openCount(){return Q.filter(i=>!resolutions[i.id]).length;}

function renderQueue(){
  const box=document.getElementById('qitems');
  const open=Q.filter(i=>!resolutions[i.id]);
  const done=Q.filter(i=>resolutions[i.id]);
  document.getElementById('qcount').textContent=open.length+' open';
  const badge=document.getElementById('qbadge');
  if(badge) badge.textContent=open.length;
  if(IS_SNAPSHOT){
    box.innerHTML='<div class="qitem"><div class="qt">snapshot</div><div class="qs">This is a published round snapshot. '+
      'The decision queue is read-only here - '+Q.length+' item(s) were open at publish time. '+
      'Rule on items in the current control center.</div></div>';
    const qr=document.getElementById('qresolved');
    if(qr) qr.textContent='';
    const eb=document.getElementById('exportBtn');
    if(eb) eb.style.display='none';
    const cb=document.getElementById('copyBtn');
    if(cb) cb.style.display='none';
    return;
  }
  let h='';
  for(const it of open){
    const pk=picked[it.id];
    const bid=btoa(unescape(encodeURIComponent(it.id))).replace(/=/g,'');
    BOX2ID['qi-'+bid]=it.id;
    h+='<div class="qitem" id="qi-'+bid+'">'+
       '<div class="qt">'+esc(it.type)+' · priority '+it.priority+'</div>'+
       '<div class="qs">'+esc(it.title)+': '+esc(it.subject)+'</div>'+
       '<div class="qe">'+esc(it.evidence.path)+(it.evidence.hits?' | '+esc(it.evidence.hits):'')+'</div>'+
       '<div class="qopts">'+it.options.map(o=>'<button class="qopt'+(pk===o?' picked':'')+'" onclick="pick(\\''+it.id+'\\',\\''+o+'\\')">'+esc(o)+'</button>').join('')+'</div>'+
       '<input class="qnote" placeholder="note (optional)" value="'+esc((resolutions[it.id]||{}).note||'')+'" oninput="note(\\''+it.id+'\\',this.value)">'+
       (pk?'<button class="qresolve" onclick="resolve(\\''+it.id+'\\')">resolve → ledger</button>':'')+
       '</div>';
  }
  if(!open.length) h='<div class="qitem"><div class="qt">queue clear</div><div class="qs">No open items — the round is caught up. '+
     'New items appear when extraction, scans or model updates surface pending judgments.</div></div>';
  h+=done.map(it=>'<div class="qitem resolved"><div class="qt">resolved this session</div><div class="qs">'+esc(it.subject)+'</div>'+
     '<div class="qe">'+esc(resolutions[it.id].resolution)+(resolutions[it.id].note?' — '+esc(resolutions[it.id].note):'')+'</div></div>').join('');
  box.innerHTML=h;
  const qr=document.getElementById('qresolved');
  if(qr) qr.textContent=done.length?done.length+' resolved (export to persist)':'';
}
function pick(id,o){picked[id]=o;renderQueue();}
function resolve(id){
  if(!picked[id])return;
  const it=Q.find(i=>i.id===id); if(!it)return;
  const noteVal=(resolutions[id]&&resolutions[id].note)||'';
  resolutions[id]={type:it.type,target:it.target,resolution:picked[id],note:noteVal,item_id:id};
  const el=boxEl(id); if(el){el.classList.add('resolving');setTimeout(renderQueue, reduced()?0:360);}else renderQueue();
}
function boxEl(id){const b=btoa(unescape(encodeURIComponent(id))).replace(/=/g,'');return document.getElementById('qi-'+b);}
function reduced(){return window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;}
function payload(){
  return {exported_at:new Date().toISOString(),round:CC_DATA.round,
    resolutions:Object.values(resolutions).filter(r=>r.resolution)};
}
function exportDecisions(){
  const blob=new Blob([JSON.stringify(payload(),null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='decisions-round-'+CC_DATA.round+'-'+Date.now()+'.json';a.click();
  URL.revokeObjectURL(a.href);
  flash('exported — drop the file in v4/data/scope/incoming/ then run rulings_applier.py');
}
function copyDecisions(){
  const t=JSON.stringify(payload(),null,2);
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(()=>flash('copied to clipboard'));}
  else{const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();flash('copied');}
}
function flash(msg){const el=document.getElementById('expstatus'); if(el) el.textContent=msg;}
document.addEventListener('input',e=>{
  if(e.target.classList&&e.target.classList.contains('qnote')){
    const box=e.target.closest('.qitem');
    if(box){const id=BOX2ID[box.id];if(id){if(!resolutions[id])resolutions[id]={};resolutions[id].note=e.target.value;}}
  }
});

// Inspector: click row → show fragments for that src_id
function inspectRow(tr){
  const fragsRaw = tr.getAttribute('data-frags');
  let frags=[];
  try{ frags=JSON.parse(fragsRaw||'[]'); }catch(e){}
  // Also try FRAG_BY_SRC by src_id
  const srcId = tr.querySelector('td.mono')?.textContent?.trim();
  if(srcId && FRAG_BY_SRC[srcId] && !frags.length) frags=FRAG_BY_SRC[srcId];
  const box=document.getElementById('inspector');
  const body=document.getElementById('insp-body');
  if(!frags.length){
    body.innerHTML='<div class="muted">No fragments for this source — it may be SKIP/PARKED or have no recognized entities. Check verbatim gate and entity patterns.</div>';
  } else {
    body.innerHTML=frags.map(f=>'<div class="frag-card"><div class="fk">'+esc(f.kind)+' — '+esc(f.entity)+' <span class="muted">conf '+f.confidence+'</span></div>'
      +'<div class="muted">anchor: '+esc(f.anchor||'')+' · '+esc(f.verbatim_sha256||'').slice(0,12)+'</div>'
      +'<div class="fv">'+esc(f.verbatim||'')+'</div></div>').join('');
  }
  box.style.display='block';
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}
function closeInspector(){document.getElementById('inspector').style.display='none';}

// Palette (Ctrl+K)
function openPalette(){
  document.getElementById('palette').style.display='flex';
  document.getElementById('pal-input').focus();
  document.getElementById('pal-input').value='';
  palSearch('');
}
function closePalette(){document.getElementById('palette').style.display='none';}
function palSearch(q){
  q=(q||'').toLowerCase();
  const res=document.getElementById('pal-results');
  if(!q){res.innerHTML='<div class="muted" style="padding:8px 12px">Type to search ledger, fragments, WORK units…</div>';return;}
  const hits=[];
  // Search constitution rows
  for(const r of (CC_DATA.constitution||[])){
    const hay=(r.id+' '+r.path+' '+(r.scope_disposition||'')+' '+(r.ke_class||'')).toLowerCase();
    if(hay.includes(q)) hits.push({label:r.id+' — '+r.path, sub:r.scope_disposition+' · '+r.status, action:()=>{showLayer('L0'); closePalette();}});
    if(hits.length>=8) break;
  }
  // Search fragments
  for(const f of FRAGS){
    const hay=(f.entity+' '+f.entity_key+' '+f.verbatim+' '+f.anchor).toLowerCase();
    if(hay.includes(q)) hits.push({label:f.entity_key+' — '+f.kind, sub:f.anchor.slice(0,60), action:()=>{showLayer('L0'); closePalette();}});
    if(hits.length>=15) break;
  }
  // Search WORK units
  for(const u of (CC_DATA.dispatch||[])){
    const hay=(u.unit_id+' '+(u.resolved_tier||'')+' '+(u.model_label||'')).toLowerCase();
    if(hay.includes(q)) hits.push({label:u.unit_id+' — '+u.resolved_tier, sub:u.model_label, action:()=>{showLayer('L3'); closePalette();}});
    if(hits.length>=20) break;
  }
  if(!hits.length) res.innerHTML='<div class="muted" style="padding:8px 12px">No results</div>';
  else res.innerHTML=hits.map((h,i)=>'<div class="pal-item'+(i===0?' sel':'')+'" onclick="this._action()" data-i="'+i+'"><b>'+esc(h.label)+'</b><div class="muted">'+esc(h.sub)+'</div></div>').join('');
  // Attach actions
  res.querySelectorAll('.pal-item').forEach((el,i)=>{ el._action=hits[i].action; el.addEventListener('click', hits[i].action); });
}
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey) && e.key==='k'){ e.preventDefault(); const pal=document.getElementById('palette'); if(pal.style.display==='none') openPalette(); else closePalette(); }
  if(e.key==='Escape'){ closePalette(); closeInspector(); }
});
document.getElementById('palette')?.addEventListener('click',e=>{ if(e.target.id==='palette') closePalette(); });

// CSV export
function exportCSV(){
  const rows=CC_DATA.constitution||[];
  const hdr='id,path,category,source_type,status,scope_disposition,ke_class,bytes,dup_of';
  const lines=[hdr].concat(rows.map(r=>[r.id,r.path,r.category,r.source_type,r.status,r.scope_disposition||'',r.ke_class||'',r.bytes,r.dup_of||''].map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')));
  const blob=new Blob([lines.join('\\n')],{type:'text/csv'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='constitution.csv';a.click();URL.revokeObjectURL(a.href);
}

// Graphs (SVG, no library)
function renderDepGraph(){
  const box=document.getElementById('dep-graph');
  if(!box) return;
  const edges=CC_DATA.dispatch ? [] : [];
  // Use CC_DATA.dispatch + fetch dependency-edges via CC_DATA if available (we embed edges separately if needed)
  // For now, render a simple topo visualization from dispatch order
  const units=CC_DATA.dispatch||[];
  if(!units.length){box.innerHTML='<div class="muted" style="padding:20px">No dispatch units</div>';return;}
  let svg='<svg viewBox="0 0 400 200" style="width:100%;height:100%"><style>.n{fill:var(--ink-1);stroke:var(--hair)} .e{stroke:var(--slate);stroke-width:1.2;marker-end:url(#arr)}</style><defs><marker id="arr" viewBox="0 0 10 10" refX=10 refY=5 markerWidth=6 markerHeight=6 orient=auto><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--slate)"/></marker></defs>';
  const cols=Math.min(units.length, 8);
  units.slice(0,12).forEach((u,i)=>{
    const x=20 + (i%cols)*48, y=30 + Math.floor(i/cols)*60;
    const col = u.resolved_tier==='STRONG'?'#6f8fae':u.resolved_tier==='FLASH'?'#9a8f78':'#6e8f5c';
    svg+=`<rect class="n" x="${x}" y="${y}" width="42" height="28" rx="4" stroke="${col}"/><text x="${x+21}" y="${y+16}" text-anchor="middle" font-size="7" fill="var(--paper)">${u.unit_id}</text>`;
    if(i>0 && i%cols!==0) svg+=`<line class="e" x1="${x-6}" y1="${y+14}" x2="${x}" y2="${y+14}"/>`;
  });
  svg+='</svg>';
  box.innerHTML=svg;
}
function renderEntityGraph(){
  const box=document.getElementById('entity-graph');
  if(!box) return;
  const frags=FRAGS.slice(0,30);
  if(!frags.length){box.innerHTML='<div class="muted" style="padding:20px">No fragments</div>';return;}
  // Co-occurrence: link entities that share same src_id
  const bySrc={};
  for(const f of frags){(bySrc[f.src_id]=bySrc[f.src_id]||[]).push(f.entity_key);}
  let svg='<svg viewBox="0 0 400 200" style="width:100%;height:100%"><style>.en{fill:var(--moss);stroke:var(--hair)} .el{stroke:var(--hair);stroke-width:.8;opacity:.5}</style>';
  const keys=[...new Set(frags.map(f=>f.entity_key).slice(0,12))];
  const pos=keys.map((k,i)=>({k, x:40+ (i%4)*90, y:40+ Math.floor(i/4)*50}));
  const pm=new Map(pos.map(p=>[p.k,p]));
  // Edges: for each src, link pairs
  const seen=new Set();
  for(const src in bySrc){
    const arr=[...new Set(bySrc[src])].slice(0,5);
    for(let i=0;i<arr.length;i++) for(let j=i+1;j<arr.length;j++){
      const a=pm.get(arr[i]), b=pm.get(arr[j]);
      if(a&&b){const key=[arr[i],arr[j]].sort().join('|'); if(!seen.has(key)){seen.add(key); svg+=`<line class="el" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;}}
    }
  }
  for(const p of pos){ svg+=`<circle class="en" cx="${p.x}" cy="${p.y}" r="18"/><text x="${p.x}" y="${p.y+3}" text-anchor="middle" font-size="6" fill="white">${esc(p.k.slice(0,10))}</text>`; }
  svg+='</svg>';
  box.innerHTML=svg;
}

// Layer switching
function showLayer(id){
  document.querySelectorAll('.layer').forEach(l=>l.style.display='none');
  const el=document.getElementById('layer-'+id); if(el)el.style.display='block';
  document.querySelectorAll('.lbtn').forEach(b=>b.classList.remove('on'));
  const rb=document.getElementById('rlb-'+id); if(rb)rb.classList.add('on');
  window.scrollTo({top:0});
  if(id==='LG'){ setTimeout(()=>{renderDepGraph(); renderEntityGraph();}, 50); }
}
// Filters
let dispSel=null;
function chipPick(el){
  const was=el.classList.contains('sel');
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('sel'));
  if(!was){el.classList.add('sel');dispSel=el.getAttribute('data-d')||null;}else dispSel=null;
  applyFilters();
}
function filterDisp(v){ if(!v)return; dispSel=v; document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('sel',c.getAttribute('data-d')===v)); showLayer('L0'); applyFilters(); }
function applyFilters(){
  const q=(document.getElementById('q').value||'').toLowerCase();
  let n=0;
  document.querySelectorAll('#const tbody tr').forEach(tr=>{
    const ok=(!q||tr.textContent.toLowerCase().includes(q))&&(!dispSel||tr.getAttribute('data-d')===dispSel);
    tr.style.display=ok?'':'none'; if(ok)n++;
  });
  const cc=document.getElementById('ccount'); if(cc) cc.textContent=n+' rows';
}
// Watch polling (if served via http, poll cc-data.json)
let watchTimer=null;
function startWatch(){
  if(location.protocol==='file:') return;
  watchTimer=setInterval(async()=>{
    try{
      const r=await fetch('cc-data.json?ts='+Date.now(), {cache:'no-store'});
      if(!r.ok) return;
      const j=await r.json();
      if(j.generated_at && j.generated_at!==CC_DATA.generated_at){
        location.reload();
      }
    }catch(e){}
  }, 3000);
}
// Boot
renderQueue();
document.getElementById('exportBtn')?.addEventListener('click', exportDecisions);
document.getElementById('copyBtn')?.addEventListener('click', copyDecisions);
if(!IS_SNAPSHOT && location.protocol!=='file:') startWatch();
// Feedback drafts (PRD §5.2) — File System Access API with download fallback
function nextDraftId(){
  const ids=(CC_DATA.drafts||[]).map(d=>d.id).filter(Boolean);
  let max=0;
  for(const id of ids){ const m=id.match(/HF-(\\d+)/); if(m) max=Math.max(max, parseInt(m[1],10)); }
  return 'HF-'+String(max+1).padStart(4,'0');
}
// JS regex uses HF-(\\d+)
async function writeFeedbackDraft(targetType, targetId, body){
  const id=nextDraftId();
  const doc={id, at:new Date().toISOString(), status:'DRAFT', provenance:'HUMAN-UI', target:{type:targetType, id:targetId}, body:{comment:body}, round_context: CC_DATA.round};
  const name=id+'.json';
  const jsonStr=JSON.stringify(doc,null,2);
  // Try File System Access API (Chrome)
  if(window.showDirectoryPicker){
    try{
      const dirHandle=await window.showDirectoryPicker({mode:'readwrite'});
      // Try to get feedback subdir
      let fbHandle;
      try{ fbHandle=await dirHandle.getDirectoryHandle('feedback', {create:true}); }catch(e){ fbHandle=dirHandle; }
      // Also handle toolkit/control-center-state/feedback path depth
      // If user picked toolkit root, we need control-center-state/feedback
      try{
        const ccHandle=await dirHandle.getDirectoryHandle('control-center-state', {create:false});
        const roundsHandle=await ccHandle.getDirectoryHandle('feedback', {create:true});
        fbHandle=roundsHandle;
      }catch(e){}
      const fileHandle=await fbHandle.getFileHandle(name, {create:true});
      const writable=await fileHandle.createWritable();
      await writable.write(jsonStr);
      await writable.close();
      alert('Draft saved: '+name+' (via File System Access API)');
      location.reload();
      return;
    }catch(e){
      if(e.name==='AbortError') return;
      console.warn('FS Access failed, falling back to download', e);
    }
  }
  // Fallback: download
  const blob=new Blob([jsonStr],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=name;
  a.click();
  URL.revokeObjectURL(a.href);
  alert('Downloaded '+name+' — drop it into toolkit/control-center-state/feedback/ then reload.\\n'+jsonStr.slice(0,300));
}
function submitFeedback(targetType, targetId, textareaId){
  const el=document.getElementById(textareaId);
  if(!el) return;
  const body=el.value.trim();
  if(!body){ alert('Please enter a comment'); return; }
  writeFeedbackDraft(targetType, targetId, body);
}
function renderDraftBadges(){
  const counts=CC_DATA.draft_counts||{};
  document.querySelectorAll('[data-fb-target]').forEach(el=>{
    const key=el.getAttribute('data-fb-target');
    const n=counts[key]||0;
    if(n>0) el.innerHTML='<span class="fb-badge">'+n+' draft(s)</span>';
  });
}
document.addEventListener('DOMContentLoaded', renderDraftBadges);
// Render graphs if LG is visible on load (not by default)
"""

def run(cfg: dict, publish: bool = False, watch: bool = False) -> None:
    """Pipeline entry point — wraps main() without argparse. Fixes O1 for run_all.py."""
    import argparse
    now = datetime.datetime.now().isoformat(timespec="seconds")
    data_dir = _resolve_data_dir(cfg)

    fd = Path(cfg["paths"]["fragments_dir"])
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"

    tracker = load_json(data_dir / "tracker.json", {"meta": {}, "rows": []})
    rows: list[dict] = tracker.get("rows", [])
    status = load_json(data_dir / "status.json", {})
    conflicts = load_json(data_dir / "conflicts.json", {"open": []})
    dup_ledger = load_json(data_dir / "dup-ledger.json", [])
    budgets = load_json(data_dir / "budget.json", [])
    esc_log = common.read_jsonl(data_dir / "escalation-log.jsonl")
    cons = load_json(data_dir / "consolidated.json", {"entities": {}, "count": 0})
    dispatch = load_json(data_dir / "dispatch-plan.json", [])
    scope_model = {}
    for p in sorted((data_dir / "scope").glob("model-*.json")) if (data_dir / "scope").exists() else []:
        scope_model = load_json(p, {}) or {}
    # Discovery clusters (blind start) — preferred over seed
    discovered_clusters = []
    disc_path = data_dir / "discovery" / "clusters.json"
    if disc_path.exists():
        disc_data = load_json(disc_path, {}) or {}
        scope_path = data_dir / "scope" / "scope.json"
        scope_data = load_json(scope_path, {}) or {}
        raw = scope_data.get("_clusters_raw")
        if raw and isinstance(raw, list):
            discovered_clusters = [c for c in raw if c.get("disposition") == "PARKED"]
        elif disc_data.get("clusters"):
            discovered_clusters = [c for c in disc_data["clusters"] if c.get("disposition") == "PARKED"]
        if disc_data.get("clusters"):
            scope_model = disc_data
    scope_json = load_json(common.V4_ROOT / "config" / "scope.json", {})
    effective_scope = scope_model if scope_model.get("clusters") else scope_json

    interviews: list[dict] = []
    for p in sorted((data_dir / "scope").glob("interview-answers-v*.json")) if (data_dir / "scope").exists() else []:
        d = load_json(p, {}) or {}
        for a in d.get("answers", []):
            interviews.append({"round": d.get("round", 0), "date": d.get("date", ""), "type": a.get("type", ""),
                                "subject": a.get("subject") or a.get("question") or a.get("id", ""),
                                "answer": a.get("answer", ""), "note": a.get("note", ""), "src": p.name})

    fragments_sample: list[dict] = []
    if (frag_dir / "_index.jsonl").exists():
        for f in common.read_jsonl(frag_dir / "_index.jsonl")[:200]:
            fragments_sample.append({k: f.get(k) for k in ("fragment_id", "src_id", "src_path", "entity", "entity_key", "kind", "anchor", "verbatim", "verbatim_sha256", "confidence", "status")})

    phases = effective_scope.get("phases", [])
    workstreams = effective_scope.get("workstreams", [])
    if not phases:
        phases = [("PH-0", "Scaffolding", "DONE"), ("PH-1", "Extraction", "ACTIVE"), ("PH-2", "Assessment", "QUEUED"), ("PH-3", "Population", "QUEUED"), ("PH-4", "Freeze", "QUEUED")]
        done_count = sum(1 for r in rows if r.get("status") == "DONE")
        if done_count > 0 and rows and done_count / len(rows) > 0.8:
            phases = [("PH-0", "Scaffolding", "DONE"), ("PH-1", "Extraction", "DONE"), ("PH-2", "Assessment", "ACTIVE"), ("PH-3", "Population", "QUEUED"), ("PH-4", "Freeze", "QUEUED")]

    gate_results: dict = {}
    try:
        from core import gates
        gate_results = gates.all_gates(cfg)
        blocking = gates.blocking_gates(cfg)
    except Exception as e:
        gate_results = {"error": [str(e)]}
        blocking = []

    is_constrained = not (len(budgets) == 1 and isinstance(budgets[0], dict) and budgets[0].get("bud_id") == "BUD-UNCONSTRAINED")
    if not budgets:
        is_constrained = False

    ke_cache = load_json(data_dir / "ke-cache.json", {})
    queue = build_queue(rows, ke_cache, effective_scope, conflicts, dup_ledger, budgets, esc_log, discovered_clusters=discovered_clusters)

    disp_counts: dict[str, int] = {}
    cat_agg: dict[str, dict[str, int]] = {}
    ke_totals: dict[str, int] = {}
    for r in rows:
        d = r.get("scope_disposition") or "UNSET"
        disp_counts[d] = disp_counts.get(d, 0) + 1
        ca = cat_agg.setdefault(r.get("category", "UNKNOWN"), {})
        ca[r.get("status", "?")] = ca.get(r.get("status", "?"), 0) + 1
        kc = r.get("ke_class") or "UNSET"
        ke_totals[kc] = ke_totals.get(kc, 0) + 1

    total_rows = len(rows) or 1
    done = sum(1 for r in rows if r.get("status") == "DONE")
    gfile_fired = sum(1 for r in rows if r.get("status") == "SKIPPED-EXACT-DUP")

    cc_round_path = data_dir / "cc-round.json"
    cc_prev = load_json(cc_round_path, {}) or {}
    round_no = max([i["round"] for i in interviews], default=0) or cc_prev.get("last_round", 0) or 1
    published = cc_prev.get("published", [])

    # Progressive state (PRD §3/§5) — union of modules_unlocked across rounds
    prog = load_progressive_state(data_dir)
    try:
        from serve import feedback_ingest as _fb
        _drafts = _fb.list_drafts()
        _draft_counts = _fb.count_by_target(_drafts)
    except Exception:
        _drafts, _draft_counts = [], {}

    # Reuse main's HTML build — delegate by building C list inline (avoid duplicating 400 lines)
    # Instead, call the same rendering logic via a helper. For now, invoke main-style render
    # by setting a synthetic args object and running the same build path.
    # Simpler: just call main() with a mocked sys.argv
    import sys as _sys
    orig_argv = _sys.argv[:]
    try:
        _sys.argv = ["control_center.py"] + (["--publish"] if publish else [])
        # We can't call main() directly since it re-loads cfg via tomlite — but we want to
        # pass our cfg. So we inline the HTML build by calling a shared helper.
        # Easiest: write a minimal _render call that uses our computed locals.
        _render_from_locals(cfg, now, data_dir, frag_dir, rows, status, conflicts, dup_ledger,
                            budgets, esc_log, cons, dispatch, effective_scope, interviews,
                            fragments_sample, phases, gate_results, blocking, is_constrained,
                            discovered_clusters, queue, disp_counts, ke_totals, total_rows, done,
                            gfile_fired, round_no, published, publish, prog, _drafts, _draft_counts)
    finally:
        _sys.argv = orig_argv


def _render_from_locals(cfg, now, data_dir, frag_dir, rows, status, conflicts, dup_ledger,
                        budgets, esc_log, cons, dispatch, effective_scope, interviews,
                        fragments_sample, phases, gate_results, blocking, is_constrained,
                        discovered_clusters, queue, disp_counts, ke_totals, total_rows, done,
                        gfile_fired, round_no, published, publish, prog=None, _drafts=None, _draft_counts=None):
    """Shared HTML rendering extracted for run() wrapper (fixes O1). Delegates to main's build."""
    # Progressive state (PRD §3/§5) — fallback preserves pre-progressive behavior
    if prog is None:
        prog = {"unlocked": {"M0", "M1", "M2", "M3", "M4", "M5"}, "latest": {}, "errors": [], "rounds": [], "is_progressive": False}
    unlocked = prog.get("unlocked", set()) or set()
    if isinstance(unlocked, list):
        unlocked = set(unlocked)
    prog_errors = prog.get("errors", [])
    is_progressive = prog.get("is_progressive", False)
    if _drafts is None:
        _drafts = []
    if _draft_counts is None:
        _draft_counts = {}
    LAYER_MODULE = {"L0": "M0", "L1": "M4", "L2": "M6", "L3": "M3", "L4": "M7", "LF": "M5", "LG": "M7", "L5": "M5"}
    def _layer_unlocked(lid: str) -> bool:
        if not is_progressive:
            return True
        req = LAYER_MODULE.get(lid, "M0")
        return req in unlocked
    def _fb_panel(target_type: str, target_id: str) -> str:
        key = f"{target_type}:{target_id}"
        n = _draft_counts.get(key, 0)
        badge = f'<span class="fb-badge">{n} draft(s)</span>' if n else '<span class="muted" data-fb-target="'+key+'"></span>'
        # Unique textarea id
        tid = f"fb-{target_type}-{target_id}"
        return (f"<details class='fb-panel'><summary class='fb-head'>Propose / Comment on {E(target_id)} {badge} "
                f"<span class='muted'>(DRAFT — visibly pending, never authoritative)</span></summary>"
                f"<textarea id='{tid}' class='fb-textarea' placeholder='Comment or propose change for {E(target_id)}...'></textarea>"
                f"<div class='fb-row'><button class='btn primary sm' onclick=\"submitFeedback('{target_type}','{target_id}','{tid}')\">Submit draft → HF-XXXX.json</button>"
                f"<span class='muted'>Writes via File System Access API (Chrome) or downloads file to drop into feedback/</span></div></details>")

    C = [f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
         f"<title>Control Center V4 MAX</title><style>{CSS}</style></head><body class='queue-open'><div class='desk'>"]

    C.append("<nav class='rail' id='rail'><div class='rail-h'>Pipeline</div>")
    for pid, name, st in phases if isinstance(phases, list) and phases and isinstance(phases[0], (list, tuple)) else []:
        dot = "dot done" if st == "DONE" else ("dot wip" if st == "ACTIVE" else "dot")
        C.append(f"<div class='rrow'><span class='{dot}'></span><span class='rlbl'>{E(name)}</span></div>")
    if not (isinstance(phases, list) and phases and isinstance(phases[0], (list, tuple))):
        for ph in phases if isinstance(phases, list) else []:
            if isinstance(ph, dict):
                st = ph.get("status", "")
                dot = "dot done" if st == "DONE" else ("dot wip" if st == "ACTIVE" else "dot")
                C.append(f"<div class='rrow'><span class='{dot}'></span><span class='rlbl'>{E(ph.get('name', ph.get('id','')))}</span></div>")

    C.append("<div class='rail-h' style='margin-top:18px'>Layers</div>")
    if _layer_unlocked("L0"):
        C.append(f"<button class='rrow lbtn on' id='rlb-L0' onclick=\"showLayer('L0')\"><span class='dot wip'></span><span class='rlbl'>L0 Scope</span></button>")
    for lid, name in [("L1","Extraction Atlas"),("L2","Consolidation"),("L3","Program"),("L4","Roadmap"),("L5","Ops & Gates"),
                       ("LF","Funnel"),("LG","Graphs")]:
        if _layer_unlocked(lid):
            C.append(f"<button class='rrow lbtn' id='rlb-{lid}' onclick=\"showLayer('{lid}')\"><span class='dot'></span><span class='rlbl'>{lid} {E(name)}</span></button>")
    C.append(f"<div class='railfoot'>{pill(f'round {round_no}', C_INFO)}<div class='muted' style='margin-top:8px'>snapshots</div>"
             + ("".join(f"<a href='history/round-{r}.html'>round {r}</a> " for r in published) or "<div class='muted'>none yet</div>") + "</div>")
    C.append("</nav>")

    C.append("<main class='canvas'><header class='chead'>")
    C.append(f"<div class='chead-top'><div><h1>Control Center <span class='vtag'>V4 MAX</span></h1>"
             f"<div class='sub'>project-agnostic — auto-discovers clusters, categories, phases — generated {E(now)} — "
             f"{pill('unconstrained', C_DIM) if not is_constrained else pill('budgeted', C_WIP)} "
             f"{pill(f'round {round_no}', C_INFO)} "
             f"<button class='qtoggle' onclick=\"document.body.classList.toggle('queue-open')\">queue <b class='qbadge' id='qbadge'>{len(queue)}</b></button> "
             f"<button class='search-btn' onclick=\"openPalette()\">⌘K search</button></div></div></div>")
    _unlock_sorted = sorted(unlocked) if isinstance(unlocked, set) else sorted(unlocked)
    C.append(f"<div class='prog-strip' style='margin:10px 0 8px;padding:8px 10px;border:1px solid {C_DIM}22;border-radius:6px;background:{C_DIM}0D;display:flex;gap:10px;align-items:center;flex-wrap:wrap'>"
             f"<span class='mono' style='font-size:11px'>unlocks: <b>{len(_unlock_sorted)}/8</b> {' '.join(_unlock_sorted) if _unlock_sorted else 'none'} "
             f"<span class='muted'>{'· progressive' if is_progressive else '· cold start (no rounds — showing all layers)'} · rounds: {len(prog.get('rounds',[]))}</span></span>"
             f"{pill(f'{len(_drafts)} draft(s)', C_WIP) if _drafts else pill('0 drafts', C_DIM)}"
             f"</div>")
    if prog_errors:
        C.append(f"<div class='card' style='border-left:3px solid {C_SKIP};margin-bottom:10px'><b>Round files skipped</b> <span class='muted'>({len(prog_errors)} malformed):</span> "
                 + "<br>".join(f"<span class='mono' style='font-size:11px'>{E(e.get('path',''))} — {E(e.get('error','')[:80])}</span>" for e in prog_errors[:5]) + "</div>")
    if _drafts:
        _bad = [d for d in _drafts if d.get("parse_error")]
        if _bad:
            C.append(f"<div class='card' style='border-left:3px solid {C_SKIP};margin-bottom:10px'><b>Feedback drafts skipped</b> <span class='muted'>({len(_bad)} malformed HF-*.json):</span> "
                     + "<br>".join(f"<span class='mono' style='font-size:11px'>{E(d.get('_path',''))} — {E(d.get('raw_error','')[:80])}</span>" for d in _bad[:5]) + "</div>")
    C.append("<div class='krow'>")
    kpis = [("files", total_rows, ""), ("done", done, "DONE"),
            ("pending", sum(1 for r in rows if r.get("status") == "PENDING"), "PENDING"),
            ("failed", sum(1 for r in rows if r.get("status") == "FAILED"), "FAILED"),
            ("fragments", len(fragments_sample) if fragments_sample else sum(r.get("fragment_count",0) for r in rows), ""),
            ("entities", cons.get("count",0) if isinstance(cons, dict) else 0, ""),
            ("conflicts", len(conflicts.get("open",[]) if isinstance(conflicts, dict) else conflicts) if isinstance(conflicts, (dict,list)) else 0, "")]
    for label, val, filt in kpis:
        col = STATUS_COLOR.get(filt, C_INFO) if filt in STATUS_COLOR else DISP_COLOR.get(filt, C_INFO)
        C.append(f"<button class='kpi' style='border-bottom-color:{col}' onclick=\"filterDisp('{E(filt)}')\" title='filter'>"
                 f"<span class='knum' style='color:{col}'>{val}</span><span class='klbl'>{E(label)}</span></button>")
    C.append("</div></header>")

    if _layer_unlocked("L0"):
        C.append("<section class='layer' id='layer-L0'>")
        C.append("<h2>Scope Constitution <span class='hsub'>every row — atomic, filterable — click any row for fragment inspector</span></h2>")
        C.append("<div class='chips'>")
        for d in ("EXTRACT", "SKIP", "REF-ONLY", "PARKED", "UNSET"):
            cnt = disp_counts.get(d, 0)
            if cnt > 0 or d in ("EXTRACT", "SKIP"):
                C.append(f"<button class='chip' data-d='{d}' onclick=\"chipPick(this)\">{E(d.lower())} <b>{cnt}</b></button>")
        C.append(f"<button class='chip' data-d='' onclick=\"chipPick(this)\">all</button>")
        C.append("<input id='q' class='search' placeholder='search path, entity, verbatim, anchor...' oninput='applyFilters()'>"
                 f"<span class='muted' id='ccount'>{total_rows} rows</span>"
                 f"<button class='btn sm' onclick=\"exportCSV()\">CSV</button></div>")

        funnel_counts = status.get("funnel", {}) if isinstance(status, dict) else {}
        if funnel_counts:
            segs = [(f"T{t}", v, TIER_COLOR.get(t, C_DIM)) for t, v in sorted(funnel_counts.items()) if v > 0]
            if segs:
                C.append(f"<div class='card' style='margin-bottom:10px'>{donut(segs, str(sum(funnel_counts.values())), 'routed')} <span class='muted'>funnel routing (escalation-log)</span></div>")

        C.append("<div class='tblwrap'><table id='const'><thead><tr><th>id</th><th>path</th><th>cat</th><th>type</th>"
                 "<th>status</th><th>disposition</th><th>ke</th><th class='num'>frags</th><th class='num'>conf</th><th>dup of</th></tr></thead><tbody>")
        qtargets = {i["target"] for i in queue}
        frag_by_src: dict[str, list[dict]] = {}
        for f in fragments_sample:
            frag_by_src.setdefault(f.get("src_id",""), []).append(f)

    # Pagination for massive corpora (I4): render first 1000 rows, lazy-load rest via JS
    _display_rows = rows[:1000] if len(rows) > 1000 else rows
    for r in _display_rows:
        d = r.get("scope_disposition") or "UNSET"
        kec = r.get("ke_class") or "-"
        st = r.get("status", "?")
        linked = " q-linked" if r["path"] in qtargets else ""
        has_frags = " has-frags" if r["id"] in frag_by_src else ""
        frags_json = E(json.dumps(frag_by_src.get(r["id"], [])[:5]))
        C.append(f"<tr data-d='{E(d)}' data-cat='{E(r.get('category',''))}' data-st='{E(st)}' data-frags='{frags_json}' class='crow{linked}{has_frags}' onclick=\"inspectRow(this)\" title=\"click for fragment inspector\">"
                 f"<td class='mono'>{E(r['id'])}</td><td class='mono'>{E(r['path'])}</td><td>{E(r.get('category',''))}</td>"
                 f"<td>{E(r.get('source_type',''))}</td><td>{pill(st, STATUS_COLOR.get(st, C_DIM))}</td>"
                 f"<td>{pill(d, DISP_COLOR.get(d, C_DIM))}</td><td class='mono'>{E(kec)}</td><td class='num mono'>{r.get('fragment_count',0)}</td>"
                 f"<td class='num mono'>{r.get('confidence',0):.2f}</td>"
                 f"<td class='mono'>{E(r.get('dup_of') or '')}</td></tr>")
    C.append("</tbody></table></div>")
    if len(rows) > 1000:
        C.append(f"<div class='card' style='margin-top:8px'><span class='muted'>Showing 1000/{len(rows)} rows — </span>"
                 f"<button class='btn sm' onclick=\"loadMoreRows()\">Load next 1000</button> "
                 f"<span class='muted'>Massive-corpus pagination (I4) — full data in CC_DATA island for search/palette</span></div>")
        C.append("""<script>function loadMoreRows(){
            const tbl=document.querySelector('#const tbody');
            if(!tbl) return;
            const shown=tbl.querySelectorAll('tr').length;
            const next=CC_DATA.constitution.slice(shown, shown+1000);
            for(const r of next){
                const tr=document.createElement('tr');
                tr.innerHTML=`<td class='mono'>${r.id}</td><td class='mono'>${r.path}</td><td>${r.category}</td><td>${r.source_type}</td><td>${r.status}</td><td>${r.scope_disposition||'UNSET'}</td><td class='mono'>${r.ke_class||'-'}</td><td class='num mono'>${r.fragment_count||0}</td><td class='num mono'>${(r.confidence||0).toFixed(2)}</td><td class='mono'>${r.dup_of||''}</td>`;
                tbl.appendChild(tr);
            }
        }</script>""")

        C.append("""<div id='inspector' class='inspector' style='display:none'><div class='insp-head'>
            <b>Fragment Inspector</b> <button class='qclose' onclick="closeInspector()">×</button></div>
            <div id='insp-body' class='insp-body'></div></div>""")

        C.append("<h2>Decisions & Interviews <span class='hsub'>case log</span></h2><div class='tl'>")
        tl = []
        for src in [common.V4_ROOT.parents[1] / "70-PROGRAM" / "06_DECISIONS.md", data_dir / "decisions-log.jsonl"]:
            if src.suffix == ".md" and src.exists():
                try:
                    for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
                        if line.startswith("| DCL-") or line.startswith("|DCL-"):
                            cells = [c.strip() for c in line.strip("|").split("|")]
                            if len(cells) >= 5:
                                tl.append({"kind": cells[0], "date": cells[1], "title": cells[2], "note": f"reversible={cells[3]} — {cells[4]}"})
                except OSError:
                    pass
        for it in interviews:
            tl.append({"kind": f"round {it['round']} — {it['type']}", "date": it["date"], "title": f"{it['subject']} → {it['answer']}", "note": it["note"] or it["src"]})
        for g in [("G-FILE","whole-file sha256 → SKIPPED-EXACT-DUP"),("G-SCOPE","scope disposition governs emission"),
                  ("G-PROV","verbatim-substring + sha + anchor"),("G-DUP","entity dedup H1-H6 + 10% audit")]:
            tl.append({"kind": g[0], "date": "-", "title": g[1], "note": "gate — see L5"})
        for t in sorted(tl, key=lambda x: x.get("date","")):
            col = C_DONE if t["kind"].startswith("DCL") else (C_INFO if "round" in t["kind"] else C_WIP)
            C.append(f"<div class='tli'><div class='tldot' style='background:{col}'></div><div class='tlbody'>"
                     f"<div>{pill(t['kind'], col)} <span class='tls'>{E(t['title'])}</span></div>"
                     f"<div class='muted'>{E(t['date'])} — {E(t['note'])}</div></div></div>")
        C.append("</div>")

        if is_constrained and isinstance(budgets, list) and budgets:
            C.append("<h2>Budgets <span class='hsub'>advisory only — never blocks</span></h2><div class='budget-bars'>")
            for b in budgets:
                if not isinstance(b, dict) or b.get("bud_id") == "BUD-UNCONSTRAINED":
                    continue
                est = b.get("est_tokens_total", b.get("est_tokens", 0))
                actual = b.get("actual_tokens_spent", b.get("actual_tokens", 0))
                pct = (actual / est * 100) if est else 0
                col = C_SKIP if pct > 80 else C_WIP if pct > 50 else C_DONE
                C.append(f"<div class='brow'><span class='mono'>{E(b.get('bud_id',''))}</span> "
                         f"<div class='btrack'><div class='bfill' style='width:{min(pct,100):.1f}%;background:{col}'></div></div> "
                         f"<span class='mono'>{actual}/{est} ({pct:.0f}%)</span></div>")
            C.append("</div>")
        else:
            C.append("<div class='card' style='margin-top:14px'><span class='muted'>Budgets: <b>unconstrained</b> — no limits configured (canon: speed primary). "
                     "Add <code>[budgets]</code> to <code>config.toml</code> for advisory tracking.</span></div>")
            C.append(_fb_panel("module", "M0"))

        C.append("</section>")

    ms_total = 6
    ms_done = 1
    L_states = [
        ("L1", "Extraction Atlas", f"Shows when first row reaches DONE — currently {done}/{total_rows} done. Will display per-source fragment inventory, entity streams, dup/conflict ledgers, provenance chains. Fragments: {len(fragments_sample)} sample loaded."),
        ("L2", "Consolidation View", f"Activates at Assessment — {len(conflicts.get('open',[]) if isinstance(conflicts, dict) else [])} conflicts; {cons.get('count',0) if isinstance(cons, dict) else 0} entities consolidated. SUPERSEDED preserved."),
        ("L3", "Program Management", f"Workstream burnup, unified backlog ({len(dispatch) if isinstance(dispatch, list) else 0} WORK units), risk register. Milestones: {ms_done}/{ms_total}."),
        ("L4", "Roadmap & Dependencies", f"Dependency graph: {len(load_json(data_dir / 'dependency-edges.json', []))} DEP edges. Code inspection: inventory via fragments/_code-index.jsonl"),
    ]
    for lid, name, copy in L_states:
        if not _layer_unlocked(lid):
            continue
        mod = LAYER_MODULE.get(lid, lid)
        C.append(f"<section class='layer' id='layer-{lid}' style='display:none'><h2>{lid} — {E(name)}</h2>"
                 f"<div class='card'><div class='empty'><span class='dot wip'></span>{E(copy)}</div></div>"
                 f"<div class='dim' style='margin-top:10px'>Atomic-first: every aggregate drills down when this layer wakes.</div>"
                 f"{_fb_panel('module', mod)}</section>")

    if _layer_unlocked("LF"):
        C.append("<section class='layer' id='layer-LF' style='display:none'><h2>LF — Funnel & Escalation</h2>")
        funnel_time = ""
        if esc_log:
            recent = esc_log[-30:]
            funnel_time = "<div class='timeline'>"
            for e in recent:
                col = TIER_COLOR.get(e.get("tier", 0), C_DIM)
                tlabel = "T" + str(e.get("tier","")) + " " + str(e.get("kind",""))
                funnel_time += f"<div class='tlane' title='{E(e.get('reason',''))}'><span class='mono'>{E(e.get('src_id','')[:12])}</span> {pill(tlabel, col)} <span class='muted'>{E(e.get('reason',''))} conf={e.get('confidence','')}</span></div>"
            funnel_time += "</div>"
        tier_segs = [(f"T{t}", v, TIER_COLOR.get(t, C_DIM)) for t, v in (status.get("funnel", {}) if isinstance(status, dict) else {}).items() if v > 0]
        if tier_segs:
            C.append(f"<div class='card'>{donut(tier_segs, str(sum(status.get('funnel', {}).values()) if isinstance(status, dict) else '0'), 'routed')}</div>")
        if funnel_time:
            C.append(f"<div class='card' style='margin-top:10px'><b>Recent escalation timeline (last 30)</b>{funnel_time}</div>")
        esc_data = load_json(data_dir / "escalations.json", [])
        if isinstance(esc_data, list) and esc_data:
            C.append(f"<div class='card' style='margin-top:10px'><b>FORGE Escalations (ESC-)</b> {len(esc_data)} records — "
                     + ", ".join(f"{pill(e.get('esc_id',''), C_INFO)} {E(e.get('trigger',''))}: {E(e.get('from_tier',''))}→{E(e.get('to_tier',''))}" for e in esc_data[:10]) + "</div>")
        C.append(_fb_panel("module", "M5"))
        C.append("</section>")

    if _layer_unlocked("LG"):
        C.append("<section class='layer' id='layer-LG' style='display:none'><h2>LG — Graphs</h2>")
        C.append("<div class='grid g2'>")
        dep_edges = load_json(data_dir / "dependency-edges.json", [])
        if isinstance(dep_edges, list) and dep_edges:
            C.append(f"<div class='card'><b>Dependency Graph</b> ({len(dep_edges)} DEP edges, {len(dispatch) if isinstance(dispatch, list) else 0} WORK units)"
                     f"<div id='dep-graph' class='graph-box'>Loading…</div>"
                     f"<div class='muted'>Topo order via core/graph.py — critical path highlighted.</div></div>")
        else:
            C.append("<div class='card'><b>Dependency Graph</b><div class='empty'>No DEP edges yet — run plan/generator.</div></div>")
        if fragments_sample:
            uniq_entities = len({f.get("entity_key","") for f in fragments_sample})
            C.append(f"<div class='card'><b>Entity Graph</b> ({uniq_entities} entities, {len(fragments_sample)} fragments sample)"
                     f"<div id='entity-graph' class='graph-box'>Loading…</div>"
                     f"<div class='muted'>Nodes=entity_key, edges=co-occurrence in same source.</div></div>")
        else:
            C.append("<div class='card'><b>Entity Graph</b><div class='empty'>No fragments yet — run t3_extract.</div></div>")
        C.append("</div>")
        if isinstance(cons, dict) and cons.get("entities"):
            req_count = sum(1 for v in cons["entities"].values() if v.get("kind") == "requirement")
            other_count = len(cons["entities"]) - req_count
            C.append(f"<div class='card' style='margin-top:10px'><b>Traceability</b> — {req_count} requirements → {other_count} capabilities/algorithms "
                     f"— G4 gate: {'<span style=\"color:#6e8f5c\">PASS</span>' if not (req_count and not other_count) else '<span style=\"color:#b0523a\">FAIL</span>'} "
                     f"<span class='muted'>(REQ → CAP/ALG)</span></div>")
        C.append(_fb_panel("module", "M7"))
        C.append("</section>")

    if _layer_unlocked("L5"):
        C.append("<section class='layer' id='layer-L5' style='display:none'><h2>L5 — Ops & Gate Health</h2>")
        C.append("<div class='card'><b>Gate Matrix G1–G8</b> <span class='muted'>G6 advisory — never blocks RATIFIED</span><div class='gate-grid'>")
        for gid in ["G1_ledger", "G2_conflicts", "G3_provenance", "G4_traceability", "G5_dup", "G6_budget_advisory", "G7_schema", "G8_state"]:
            errs = gate_results.get(gid, [])
            is_advisory = gid == "G6_budget_advisory"
            if errs:
                col = C_WIP if is_advisory else C_SKIP
                label = "ADVISORY" if is_advisory else "FAIL"
                C.append(f"<div class='gate-cell fail' style='border-left-color:{col}'><b>{E(gid)}</b> {pill(label, col)}<div class='muted'>{E(errs[0][:120])}</div></div>")
            else:
                C.append(f"<div class='gate-cell pass'><b>{E(gid)}</b> {pill('PASS', C_DONE)}</div>")
        C.append("</div></div>")
        if blocking:
            C.append(f"<div class='card' style='margin-top:10px;border-left:3px solid {C_SKIP}'><b>Blocking Ratification</b><div class='muted'>" + "<br>".join(E(b) for b in blocking[:5]) + "</div></div>")
        else:
            C.append(f"<div class='card' style='margin-top:10px;border-left:3px solid {C_DONE}'><b>Ratification: <span style='color:{C_DONE}'>READY</span></b> <span class='muted'>All blocking gates pass. G6 advisory does not block.</span></div>")

        C.append("<div class='grid g3' style='margin-top:10px'>")
        C.append(f"<div class='card'><b>Gates fired</b>"
                 + "".join(f"<div class='stg'>{pill(k, C_INFO)} <b>{v}</b></div>" for k, v in
                           [("G-FILE", gfile_fired), ("G-SCOPE", sum(disp_counts.values())), ("G-DUP", len(dup_ledger) if isinstance(dup_ledger, list) else 0)]) + "</div>")
        C.append("<div class='card'><b>Audit sampling</b><div class='dim'>Every 10th gated skip is flagged for human spot-check. Sample queue: derived from G-DUP ledger — inspect in L0 via filter.</div></div>")
        C.append(f"<div class='card'><b>Regeneration</b><div class='dim'>built {E(now)} — snapshots: " + (", ".join(str(r) for r in published) or "none") + "</div>"
                 f"<div class='dim' style='margin-top:6px'>Watch: <code>python serve/control_center.py --watch</code> polls every 3s.</div></div>")
        C.append("</div>")
        C.append(_fb_panel("module", "M5"))
        C.append("</section>")

    C.append("</main>")

    C.append(f"<aside class='queue' id='queue'><div class='qhead'>Decision Queue <span class='muted' id='qcount'></span>"
             f"<button class='qclose' onclick=\"document.body.classList.remove('queue-open')\" title='collapse'>×</button></div>"
             f"<div class='qitems' id='qitems'></div>"
             f"<div class='qfoot'><div class='dim' id='qresolved'></div>"
             f"<button class='btn primary' id='exportBtn'>Export decisions</button>"
             f"<button class='btn' id='copyBtn'>Copy JSON</button>"
             f"<div class='muted' id='expstatus'></div></div></aside>")
    C.append("</div>")

    C.append("""<div id='palette' class='palette' style='display:none'><div class='pal-box'>
        <input id='pal-input' class='pal-input' placeholder='Search path, entity, verbatim, anchor...' oninput='palSearch(this.value)'>
        <div id='pal-results' class='pal-results'></div>
        <div class='muted' style='padding:6px 10px'>Ctrl+K to open, Esc to close — searches ledger, fragments, and WORK units</div>
    </div></div>""")

    cc_data = {
        "generated_at": now, "round": round_no, "published": published, "is_current": True,
        "is_constrained": is_constrained,
        "dispositions": disp_counts, "queue": queue,
        "constitution": [{k: r.get(k) for k in ("id", "path", "category", "source_type", "status", "scope_disposition", "scope_cluster", "ke_class", "bytes", "sha256", "dup_of", "fragment_count", "confidence")} for r in rows],
        "fragments_sample": fragments_sample,
        "ke_class_of": {r["path"]: r.get("ke_class") for r in rows if r.get("ke_class")},
        "dispatch": dispatch if isinstance(dispatch, list) else [],
        "budgets": budgets if isinstance(budgets, list) else [],
        "gates": gate_results, "blocking": blocking,
        "conflicts": conflicts if isinstance(conflicts, dict) else {"open": conflicts},
        "entities_count": cons.get("count", 0) if isinstance(cons, dict) else 0,
        "drafts": _drafts,
        "draft_counts": {f"{k[0]}:{k[1]}": v for k, v in _draft_counts.items()},
        "prog": {"unlocked": sorted(list(unlocked)), "is_progressive": is_progressive, "rounds": len(prog.get("rounds",[])), "errors": prog_errors},
    }
    island = json.dumps(cc_data, ensure_ascii=True).replace("</", "<\\/").replace("<!--", "<\\!--")
    C.append(f"<footer class='foot'><div class='loopdim'><b>Decision loop:</b> rule on open items in the queue → "
             f"<span class='mono'>Export decisions</span> → drop the file in <span class='mono'>v4/data/scope/incoming/</span> → "
             f"agent runs <span class='mono'>serve/rulings_applier.py</span> → rebuild.</div>"
             f"<div class='muted'>Derived-only — never hand-edit. Rebuild: <code>python -m serve.control_center</code> "
             f"(<code>--publish</code> for snapshot, <code>--watch</code> for live poll). Data island CC_DATA embedded below.</div></footer>")
    C.append(f"<script>const CC_DATA = {island};\n{JS}</script></body></html>")

    html_text = "\n".join(C)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_primary = data_dir / "control-center.html"
    out_primary.write_text(html_text, encoding="utf-8")
    try:
        corpus_root = Path(cfg["paths"]["corpus_root"])
        if not corpus_root.is_absolute():
            corpus_root = (common.V4_ROOT / corpus_root).resolve()
        is_legacy = (corpus_root / "50-TOOLKIT").exists() or (corpus_root / "60-CANONICAL").exists()
        if is_legacy and "data-lab" not in str(corpus_root):
            docpack_cc = corpus_root / "60-CANONICAL" / "DOCPACK" / "CONTROL-CENTER.html"
            if not corpus_root.exists():
                docpack_cc = common.V4_ROOT.parents[1] / "60-CANONICAL" / "DOCPACK" / "CONTROL-CENTER.html"
            docpack_cc.parent.mkdir(parents=True, exist_ok=True)
            docpack_cc.write_text(html_text, encoding="utf-8")
    except Exception:
        pass
    common.write_json(data_dir / "cc-data.json", cc_data)

    if publish:
        hist = data_dir / "history"
        hist.mkdir(parents=True, exist_ok=True)
        (hist / f"round-{round_no}.html").write_text(html_text, encoding="utf-8")
        published_set = sorted(set(published + [round_no]))
        common.write_json(cc_round_path, {"last_round": round_no, "published": published_set})
        print(f"published snapshot: history/round-{round_no}.html")
    print(f"control center V4 MAX: {out_primary} ({out_primary.stat().st_size} bytes) round={round_no} queue={len(queue)} rows={len(rows)} frags={len(fragments_sample)}")


if __name__ == '__main__':
    main()