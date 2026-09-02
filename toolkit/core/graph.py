"""V4 Core — Dependency graph utilities: topo sort + ready-task selector.

Kahn's algorithm. Project-agnostic. No deps.
"""
from __future__ import annotations


def topo_sort(tasks: list[dict]) -> list[dict]:
    """Kahn's algorithm. tasks: [{id, deps:[ids]}]. Raises on cycle."""
    by_id = {t["id"]: t for t in tasks}
    indeg = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t.get("deps", []):
            if d in by_id:
                indeg[t["id"]] += 1
                adj[d].append(t["id"])
    queue = sorted([i for i, d in indeg.items() if d == 0])
    order = []
    while queue:
        n = queue.pop(0)
        order.append(by_id[n])
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
        queue.sort()
    if len(order) != len(tasks):
        raise ValueError("dependency cycle detected")
    return order


def ready_tasks(tasks: list[dict], done: set) -> list[dict]:
    """Tasks whose dependencies are all satisfied."""
    task_ids = {x["id"] for x in tasks}
    out = []
    for t in tasks:
        if t["id"] in done:
            continue
        if all(d in done for d in t.get("deps", []) if d in task_ids):
            out.append(t)
    return out
