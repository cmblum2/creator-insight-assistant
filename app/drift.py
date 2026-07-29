"""Drift monitoring — "how do you know it still works next month?"

Snapshots the signals that reveal a stale model and compares them to a saved baseline:
  * INPUT drift  — PSI (population stability index) on roster features (GMV, followers) vs baseline.
                   PSI < 0.10 stable · 0.10-0.25 moderate · > 0.25 significant.
  * MODEL skill  — Spearman(rank, refund-adjusted lift) vs baseline; a decay is the real alarm.
  * OUTCOME      — hit rate (% ROI-positive) vs baseline.
  * FRESHNESS    — label + comment-corpus counts.
First run writes the baseline (data/drift_baseline.json); later runs report deltas + flags.
"""
import json
import os

import numpy as np
import pandas as pd

from app.config import CONTRACT

BASELINE = "data/drift_baseline.json"
_PSI_SIGNIFICANT = 0.25


def _psi(base_edges, base_props, actual):
    a = np.asarray(actual, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return None
    cnt, _ = np.histogram(a, bins=base_edges)
    props = np.clip(cnt / max(cnt.sum(), 1), 1e-4, None)
    b = np.clip(np.asarray(base_props, dtype=float), 1e-4, None)
    return float(np.sum((props - b) * np.log(props / b)))


def _bins(values, bins=10):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < bins:
        return None
    edges = np.quantile(v, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    cnt, _ = np.histogram(v, bins=edges)
    return {"edges": edges.tolist(), "props": (cnt / max(cnt.sum(), 1)).tolist()}


def _features():
    """Numeric model inputs to watch for distribution drift."""
    out = {}
    try:
        r = pd.read_csv(CONTRACT["roster"])
        out["gmv_30d"] = pd.to_numeric(r["total_gmv_30d"], errors="coerce").dropna().tolist()
    except Exception:
        pass
    try:
        c = pd.read_csv("data/creators.csv")
        out["followers"] = pd.to_numeric(c["followers"], errors="coerce").dropna().tolist()
    except Exception:
        pass
    return out


def _skill_and_hit():
    from scipy.stats import spearmanr
    out = {"skill": None, "hit_rate": None, "n_labels": 0, "corpus_comments": None}
    try:
        om = pd.read_csv(CONTRACT["outcomes"])
        col = "did_lift_refadj" if "did_lift_refadj" in om.columns else "did_lift"
        out["n_labels"] = int(len(om))
        j = om.dropna(subset=["rank_position", col])
        if len(j) >= 5:
            out["skill"] = round(float(spearmanr(j["rank_position"], j[col]).correlation), 3)
    except Exception:
        pass
    try:
        from app.economics import unit_economics
        out["hit_rate"] = unit_economics().get("pct_roi_positive")
    except Exception:
        pass
    try:
        out["corpus_comments"] = int(len(pd.read_csv(CONTRACT.get("comments", "data/comments.csv"))))
    except Exception:
        pass
    return out


def snapshot():
    feats = _features()
    sk = _skill_and_hit()
    return {"features": {c: _bins(v) for c, v in feats.items() if _bins(v)},
            "skill": sk["skill"], "hit_rate": sk["hit_rate"], "n_labels": sk["n_labels"],
            "corpus_comments": sk["corpus_comments"]}


def drift_report():
    snap = snapshot()
    if not os.path.exists(BASELINE):
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        return {"status": "baseline_written", "note": "first run — saved baseline; drift reported next run.",
                "skill": snap["skill"], "hit_rate": snap["hit_rate"], "n_labels": snap["n_labels"]}
    base = json.load(open(BASELINE, encoding="utf-8"))
    feats_now = _features()
    psi = {}
    for c, b in (base.get("features") or {}).items():
        if c in feats_now:
            v = _psi(b["edges"], b["props"], feats_now[c])
            if v is not None:
                psi[c] = round(v, 3)
    worst = max(psi.items(), key=lambda kv: kv[1]) if psi else (None, 0.0)
    flags = []
    if worst[1] > _PSI_SIGNIFICANT:
        flags.append(f"INPUT drift: '{worst[0]}' PSI={worst[1]}")
    if base.get("skill") is not None and snap["skill"] is not None and snap["skill"] - base["skill"] > 0.15:
        flags.append(f"SKILL decay: {base['skill']} -> {snap['skill']}")
    if base.get("hit_rate") and snap["hit_rate"] and snap["hit_rate"] < base["hit_rate"] - 0.05:
        flags.append(f"HIT-RATE drop: {base['hit_rate']:.0%} -> {snap['hit_rate']:.0%}")
    return {
        "status": "ok" if not flags else "drift_detected",
        "psi_by_feature": psi, "max_psi": {"feature": worst[0], "value": worst[1]},
        "skill": {"baseline": base.get("skill"), "current": snap["skill"]},
        "hit_rate": {"baseline": base.get("hit_rate"), "current": snap["hit_rate"]},
        "n_labels": {"baseline": base.get("n_labels"), "current": snap["n_labels"]},
        "flags": flags,
        "note": "PSI<0.10 stable, 0.10-0.25 moderate, >0.25 significant. Skill negative (more negative "
                "= better); a rise toward 0 flags decay.",
    }
