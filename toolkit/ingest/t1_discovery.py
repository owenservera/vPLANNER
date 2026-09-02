#!/usr/bin/env python3
"""V4 Ingest — T1 DISCOVERY. Blind-start engine: heading n-gram + TF-IDF clustering.

Reads scan-model sample (headings + head lines) and discovers:
  1. Clusters  (C1..CN) via heading Jaccard + TF-IDF cosine — stdlib only
  2. Entity vocab → data/entity-packs/discovered.json
  3. Scope seed  → data/scope/scope.json (PARKED, awaiting ratification)
  4. Summary     → data/discovery/discovery-summary.json

Deterministic. No LLM. No embeddings. No network.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, funnel

# ---------------------------------------------------------------------------
# Stopwords + tokenization
# ---------------------------------------------------------------------------
STOPWORDS = frozenset(
    "the a an and or is are was were of to in on for with as by at from "
    "be been being has have had do does did will would can could should "
    "this that these those it its if then than into over under about "
    "all any each more most other some such no nor not only own same so than too very "
    "just don now".split()
)

WORD_RE = re.compile(r"[a-zA-Z]{2,}")


def tokenize(text: str) -> list[str]:
    toks = [w.lower() for w in WORD_RE.findall(text)]
    return [w for w in toks if w not in STOPWORDS and len(w) >= 3]


def heading_tokens(entry: dict) -> set[str]:
    """All words from title + h2_headings for this sample entry."""
    parts: list[str] = []
    if entry.get("title"):
        parts.append(entry["title"])
    for h in entry.get("h2_headings", []):
        parts.append(h)
    return set(tokenize(" ".join(parts)))


def head_line_tokens(entry: dict) -> list[str]:
    return tokenize(" ".join(entry.get("head_lines", [])))


# ---------------------------------------------------------------------------
# TF-IDF utilities
# ---------------------------------------------------------------------------

def build_tfidf(entries: list[dict]) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Return (tfidf_per_entry, idf)."""
    # Document = one sample entry's combined tokens
    doc_tokens: list[Counter] = []
    df: Counter = Counter()
    for e in entries:
        toks = tokenize(
            (e.get("title") or "") + " " +
            " ".join(e.get("h2_headings", [])) + " " +
            " ".join(e.get("head_lines", []))
        )
        c = Counter(toks)
        doc_tokens.append(c)
        for w in c:
            df[w] += 1

    N = len(entries) or 1
    idf: dict[str, float] = {}
    for w, cnt in df.items():
        idf[w] = math.log(N / cnt) if cnt else 0.0

    tfidf: list[dict[str, float]] = []
    for c in doc_tokens:
        total = sum(c.values()) or 1
        vec: dict[str, float] = {}
        for w, cnt in c.items():
            vec[w] = (cnt / total) * idf[w]
        tfidf.append(vec)
    return tfidf, idf


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # sparse dot
    dot = sum(a[w] * b.get(w, 0.0) for w in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def cluster_entries(
    entries: list[dict],
    tfidf: list[dict[str, float]],
    threshold: float = 0.22,
    max_clusters: int = 8,
) -> list[list[int]]:
    """Greedy single-link agglomerative by combined heading-Jaccard + TF-IDF cosine."""
    if not entries:
        return []

    heading_sets: list[set[str]] = [heading_tokens(e) for e in entries]
    clusters: list[list[int]] = []

    for idx in range(len(entries)):
        best_ci = -1
        best_score = -1.0
        for ci, members in enumerate(clusters):
            # score vs cluster = max over members (single-link)
            s = 0.0
            for midx in members:
                hj = jaccard(heading_sets[idx], heading_sets[midx])
                cs = cosine(tfidf[idx], tfidf[midx])
                combined = 0.5 * hj + 0.5 * cs
                if combined > s:
                    s = combined
            if s > best_score:
                best_score = s
                best_ci = ci
        if best_ci >= 0 and best_score >= threshold:
            clusters[best_ci].append(idx)
        else:
            clusters.append([idx])

    # Cap: merge smallest clusters into nearest neighbor until within limit
    while len(clusters) > max_clusters:
        # merge the smallest cluster into its nearest neighbor
        smallest = min(range(len(clusters)), key=lambda i: len(clusters[i]))
        # find nearest other cluster by centroid similarity
        best_other = -1
        best_sim = -1.0
        for oi in range(len(clusters)):
            if oi == smallest:
                continue
            # centroid = mean tfidf
            sim = 0.0
            cnt = 0
            for a in clusters[smallest]:
                for b in clusters[oi]:
                    hj = jaccard(heading_sets[a], heading_sets[b])
                    cs = cosine(tfidf[a], tfidf[b])
                    sim += 0.5 * hj + 0.5 * cs
                    cnt += 1
            avg = sim / cnt if cnt else 0.0
            if avg > best_sim:
                best_sim = avg
                best_other = oi
        # merge smallest into best_other
        clusters[best_other].extend(clusters[smallest])
        clusters.pop(smallest)

    return clusters


# ---------------------------------------------------------------------------
# Entity vocab generation
# ---------------------------------------------------------------------------

def generate_entity_pack(
    entries: list[dict],
    clusters: list[list[int]],
) -> dict[str, list[str]]:
    """Heading n-grams (2-3 words) that appear in ≥2 entries → component/interface patterns.
    Plus observed ID-like token shapes.
    """
    # Collect heading phrases as they appear (preserve case for pattern)
    phrase_counts: Counter = Counter()
    phrase_example: dict[str, str] = {}
    id_tokens: set[str] = set()

    ID_RE = re.compile(r"\b[A-Z]{2,}-\d+\b|\b[A-Z][a-zA-Z]+(?:Service|Engine|Store|Controller|Manager|Handler|Provider|Contract|Interface|API|Schema)\b")

    for e in entries:
        headings: list[str] = []
        if e.get("title"):
            headings.append(e["title"])
        headings.extend(e.get("h2_headings", []))
        for h in headings:
            toks = [w for w in re.findall(r"[A-Za-z]{2,}", h)]
            # n-grams
            for n in (2, 3):
                for i in range(len(toks) - n + 1):
                    phrase = " ".join(toks[i:i+n])
                    key = phrase.lower()
                    phrase_counts[key] += 1
                    if key not in phrase_example:
                        phrase_example[key] = phrase
            # ID-like
            for m in ID_RE.finditer(h):
                id_tokens.add(m.group(0))

        for line in e.get("head_lines", []):
            for m in ID_RE.finditer(line):
                id_tokens.add(m.group(0))

    # Keep phrases with count >= 2
    kept_phrases = {k: v for k, v in phrase_counts.items() if v >= 2}

    pack: dict[str, list[str]] = {}

    if kept_phrases:
        # Use kept phrases as component patterns (word-boundary, case-insensitive)
        component_pats: list[str] = []
        interface_pats: list[str] = []
        for key, cnt in sorted(kept_phrases.items(), key=lambda x: (-x[1], x[0]))[:24]:
            words = key.split()
            # Build regex: \bWord1[ -]?Word2(?:[ -]?Word3)?\b
            pat = r"\b" + r"[ \-_]*".join(re.escape(w) for w in words) + r"\b"
            phrase = phrase_example[key]
            # Heuristic: if phrase contains API/Contract/Interface/Schema → interface
            if any(kw in phrase.lower() for kw in ("api", "contract", "interface", "schema")):
                interface_pats.append(pat)
            else:
                component_pats.append(pat)
        if component_pats:
            pack["component"] = component_pats
        if interface_pats:
            pack["interface"] = interface_pats

        # Requirement-like: headings that look like "Requirement X" or similar
        # Use a generic capture for discovered requirement phrasing
        req_keywords: list[str] = []
        for key in kept_phrases:
            if key.startswith("requirement ") or key.startswith("requirements "):
                req_keywords.append(key)
        if req_keywords:
            pack["requirement"] = [r"\b" + re.escape(k) + r"\b" for k in req_keywords[:8]]

    if id_tokens:
        # Observed ID shapes — expose as additional patterns for their kinds
        # e.g. observed "REQ-001" → add a pattern for that prefix
        prefixes: set[str] = set()
        for tok in id_tokens:
            m = re.match(r"([A-Z]{2,})-\d+", tok)
            if m:
                prefixes.add(m.group(1))
        for pfx in sorted(prefixes):
            if pfx in ("REQ", "DOC", "DCL", "ADR", "RSK", "RISK"):
                kind = {"REQ": "requirement", "DOC": "requirement", "DCL": "decision", "ADR": "decision", "RSK": "risk", "RISK": "risk"}[pfx]
                pat = rf"\b{re.escape(pfx)}-\d+\b"
                pack.setdefault(kind, []).append(pat)

    # Dedup within each kind
    for k in list(pack.keys()):
        pack[k] = list(dict.fromkeys(pack[k]))

    return pack


# ---------------------------------------------------------------------------
# Build cluster metadata
# ---------------------------------------------------------------------------

def build_cluster_objects(
    entries: list[dict],
    clusters: list[list[int]],
    tfidf: list[dict[str, float]],
    idf: dict[str, float],
) -> tuple[list[dict], dict[str, str]]:
    """Return (cluster_objs, path_hints)."""
    objs: list[dict] = []
    path_hints: dict[str, str] = {}

    for ci, members in enumerate(clusters):
        cid = f"C{ci + 1}"
        member_entries = [entries[i] for i in members]
        paths = [e["path"] for e in member_entries]

        # Keywords: top TF-IDF terms aggregated across members
        agg: Counter = Counter()
        for midx in members:
            for w, score in tfidf[midx].items():
                agg[w] += score
        top_kw = [w for w, _ in agg.most_common(5)]
        name = " ".join(w.capitalize() for w in top_kw[:3]) if top_kw else f"Cluster {ci+1}"

        # evidence: count + example heading
        example_heading = ""
        for e in member_entries:
            if e.get("h2_headings"):
                example_heading = e["h2_headings"][0][:80]
                break
            if e.get("title"):
                example_heading = e["title"][:80]
                break

        evidence = [
            f"{len(members)} file(s) clustered by headings + TF-IDF (threshold derived)",
            f"example heading: \"{example_heading}\"" if example_heading else "no headings — grouped by head-line vocabulary",
            f"keywords: {', '.join(top_kw[:5])}" if top_kw else "",
        ]
        evidence = [e for e in evidence if e]

        # path_hints: majority category among members
        cats = Counter(e.get("category", "UNKNOWN") for e in member_entries)
        majority_cat = cats.most_common(1)[0][0] if cats else "UNKNOWN"
        # Only set hint if majority dominates
        if cats[majority_cat] >= len(members) * 0.5:
            path_hints[majority_cat] = cid

        # confidence: mean pairwise combined score within cluster (1-member clusters = 0.5 baseline)
        if len(members) <= 1:
            conf = 0.45
        else:
            heading_sets = [heading_tokens(entries[m]) for m in members]
            scores: list[float] = []
            for a_i, a in enumerate(members):
                for b in members[a_i+1:]:
                    hj = jaccard(heading_sets[members.index(a)], heading_sets[members.index(b)])
                    cs = cosine(tfidf[a], tfidf[b])
                    scores.append(0.5 * hj + 0.5 * cs)
            conf = sum(scores) / len(scores) if scores else 0.45

        objs.append({
            "id": cid,
            "name": name,
            "evidence": evidence,
            "member_paths": paths,
            "keywords": top_kw,
            "disposition": "PARKED",
            "confidence": round(conf, 3),
            "source": "discovered",
        })

    return objs, path_hints


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(cfg: dict) -> dict:
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    data_dir.mkdir(parents=True, exist_ok=True)

    discovery_dir = data_dir / "discovery"
    discovery_dir.mkdir(parents=True, exist_ok=True)

    scope_dir = data_dir / "scope"
    scope_dir.mkdir(parents=True, exist_ok=True)

    pack_dir = data_dir / "entity-packs"
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Config
    disc_cfg = cfg.get("discovery", {})
    threshold = float(disc_cfg.get("cluster_threshold", 0.22))
    max_clusters = int(disc_cfg.get("max_clusters", 8))
    min_cluster_size = int(disc_cfg.get("min_cluster_size", 1))

    # Check if scope already ratified — don't overwrite
    scope_path = scope_dir / "scope.json"
    if scope_path.exists():
        existing_scope = common.read_json(scope_path, default={})
        if existing_scope.get("status") == "RATIFIED":
            common.log("discovery: scope.json already RATIFIED — skipping (delete to re-discover)", "info")
            return {"skipped": "ratified"}

    # Load sample — prefer scan-model.json, fall back to direct corpus scan
    entries: list[dict] = []
    scan_model = scope_dir / "scan-model.json"

    if scan_model.exists():
        model = common.read_json(scan_model, default={})
        entries = model.get("sample", [])
        if not entries:
            # Legacy shape: maybe "sample" is top-level list
            entries = model.get("entries", [])

    if not entries:
        # Fallback: generate a sample directly (no scan-model)
        common.log("discovery: no scan-model sample — sampling directly from tracker", "warn")
        from core import ledger as _ledger
        try:
            tracker = _ledger.load(cfg)
            corpus_root = Path(tracker["meta"]["corpus_root"]) if tracker.get("meta", {}).get("corpus_root") else None
            if corpus_root is None:
                cr = cfg["paths"]["corpus_root"]
                corpus_root = (common.V4_ROOT / cr).resolve() if not Path(cr).is_absolute() else Path(cr)
            # Sample up to 40 files stratifically
            import random
            rng = random.Random(int(cfg.get("limits", {}).get("sample_seed", 42)))
            from collections import defaultdict as _dd
            by_cat: dict[str, list[dict]] = _dd(list)
            for r in tracker.get("rows", []):
                if r.get("source_type") in ("DOC", "ARCHIVE", "TRANSCRIPT") and r.get("status") not in ("FAILED", "SKIPPED-EXACT-DUP"):
                    by_cat.setdefault(r.get("category", "UNKNOWN"), []).append(r)
            per_cat = int(cfg.get("limits", {}).get("sample_per_category", 8))
            # Lightweight summarize — headings + head lines
            import re as _re
            H2_RE = _re.compile(r"^##\s+(.+)$", _re.MULTILINE)
            H1_RE = _re.compile(r"^#\s+(.+)$", _re.MULTILINE)
            for cat in sorted(by_cat):
                take = rng.sample(by_cat[cat], min(per_cat, len(by_cat[cat])))
                for r in take:
                    p = corpus_root / r["path"]
                    entry: dict = {"path": r["path"], "category": cat, "bytes": r.get("bytes", 0)}
                    try:
                        text = common.read_text(p)
                        h2s = [m.group(1).strip()[:110] for m in H2_RE.finditer(text)][:30]
                        h1m = H1_RE.search(text)
                        entry["title"] = (h1m.group(1).strip()[:110] if h1m else r["path"])
                        entry["h2_headings"] = h2s
                        entry["head_lines"] = [ln.strip()[:120] for ln in text.splitlines() if ln.strip()][:6]
                    except OSError:
                        entry["title"] = r["path"]
                        entry["h2_headings"] = []
                        entry["head_lines"] = []
                    entries.append(entry)
        except Exception as e:
            common.log(f"discovery: fallback sampling failed: {e}", "warn")

    if not entries:
        common.log("discovery: no entries to cluster — emitting empty scope template", "warn")
        # Emit empty but valid artifacts so downstream doesn't crash
        common.write_json(discovery_dir / "clusters.json", {"method": "heading_jaccard+tfidf_cosine", "threshold": threshold, "clusters": [], "path_hints": {}, "ts": common.now_iso()})
        common.write_json(scope_path, {"_comment": "Discovery found no clusterable content — all dispositions PARKED pending interview", "status": "DRAFT", "compiled": common.now_iso(), "project_statement": "No heading vocabulary discovered — manual scope required.", "clusters": {}, "path_hints": {}})
        common.write_json(discovery_dir / "discovery-summary.json", {"method": "heading_jaccard+tfidf_cosine", "threshold": threshold, "num_clusters": 0, "num_patterns": 0, "sample_size": 0, "ts": common.now_iso()})
        common.write_json(pack_dir / "discovered.json", {"_comment": "No patterns discovered — extraction will use generic.json fallback"})
        return {"clusters": [], "patterns": {}}

    # Build TF-IDF + cluster
    tfidf, idf = build_tfidf(entries)
    raw_clusters = cluster_entries(entries, tfidf, threshold=threshold, max_clusters=max_clusters)

    # Filter tiny clusters if needed
    if min_cluster_size > 1:
        raw_clusters = [c for c in raw_clusters if len(c) >= min_cluster_size]
        if not raw_clusters and entries:
            # Keep at least one cluster if everything was filtered
            raw_clusters = cluster_entries(entries, tfidf, threshold=threshold * 0.6, max_clusters=max_clusters)

    cluster_objs, path_hints = build_cluster_objects(entries, raw_clusters, tfidf, idf)
    discovered_pack = generate_entity_pack(entries, raw_clusters)

    # Write artifacts
    common.write_json(discovery_dir / "clusters.json", {
        "method": "heading_jaccard(0.5)+tfidf_cosine(0.5) single-link",
        "threshold": threshold,
        "max_clusters": max_clusters,
        "clusters": cluster_objs,
        "path_hints": path_hints,
        "ts": common.now_iso(),
        "sample_size": len(entries),
    })

    # Scope seed (PARKED — awaiting ratification)
    scope_obj: dict = {
        "_comment": "DISCOVERED from corpus headings — dispositions PARKED until ratified via Control Center queue. Edit or rule via queue → rulings_applier.",
        "status": "DRAFT",
        "compiled": common.now_iso(),
        "project_statement": f"Discovered {len(cluster_objs)} cluster(s) from {len(entries)} sampled files — ratify dispositions to begin extraction.",
        "clusters": {c["id"]: {"name": c["name"], "disposition": c["disposition"], "evidence": c["evidence"], "member_paths": c["member_paths"], "keywords": c["keywords"]} for c in cluster_objs},
        "path_hints": path_hints,
        "_clusters_raw": cluster_objs,  # full objs for CC queue
    }
    common.write_json(scope_path, scope_obj)

    common.write_json(pack_dir / "discovered.json", {
        "_comment": "Generated from heading n-grams — loaded alongside generic.json",
        "_source": "t1_discovery heading_vocab",
        "_sample_size": len(entries),
        **discovered_pack,
    })

    common.write_json(discovery_dir / "discovery-summary.json", {
        "method": "heading_jaccard+tfidf_cosine single-link",
        "threshold": threshold,
        "num_clusters": len(cluster_objs),
        "num_patterns": sum(len(v) for v in discovered_pack.values()),
        "sample_size": len(entries),
        "ts": common.now_iso(),
    })

    common.log(f"discovery: {len(cluster_objs)} cluster(s) from {len(entries)} sampled files — {sum(len(v) for v in discovered_pack.values())} patterns generated", "ok")
    for c in cluster_objs:
        common.log(f"  {c['id']}: {c['name']} — {len(c['member_paths'])} files — keywords: {', '.join(c['keywords'][:4])} → PARKED", "info")

    eng = funnel.EscalationEngine(cfg)
    eng.dispatch(funnel.WorkItem(kind="discovery", confidence=0.7 if cluster_objs else 0.3,
                                  detail=f"{len(cluster_objs)} clusters, {sum(len(v) for v in discovered_pack.values())} patterns from {len(entries)} sampled"))

    return {"clusters": cluster_objs, "path_hints": path_hints, "patterns": discovered_pack}


if __name__ == "__main__":
    from core import tomlite
    run(tomlite.load())
