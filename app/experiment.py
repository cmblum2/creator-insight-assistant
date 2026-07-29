"""Randomized-holdout design + analysis harness — how you PROVE the engine drives incremental value.

Everything else is observational (matched-control style) or backtested. The gold standard a diligence
lens asks for is a controlled test: randomly split eligible creators into ENGINE-picked (treatment) vs
STATUS-QUO-picked (control), seed both, and compare realized incremental profit. This module sizes the
test up front (power) and reads it out with a CI + significance. Pure + data-free so it's usable the
day a holdout runs.
"""
import math


def required_n_per_arm(mde, sigma, alpha=0.05, power=0.80):
    """Per-arm n to detect a mean per-sample profit difference `mde` given outcome std `sigma`."""
    if mde <= 0 or sigma <= 0:
        return None
    return int(math.ceil(2 * (_z(1 - alpha / 2) + _z(power)) ** 2 * (sigma ** 2) / (mde ** 2)))


def required_n_per_arm_proportion(p0, p1, alpha=0.05, power=0.80):
    """Per-arm n to detect a hit-rate lift p0->p1. When outcomes are power-law, testing the PROPORTION
    of winning samples is far better-powered than the mean — the design the distribution calls for."""
    if not (0 < p0 < 1 and 0 < p1 < 1) or p1 == p0:
        return None
    z_a, z_b, pbar = _z(1 - alpha / 2), _z(power), (p0 + p1) / 2
    num = (z_a * math.sqrt(2 * pbar * (1 - pbar)) + z_b * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2
    return int(math.ceil(num / (p1 - p0) ** 2))


def holdout_lift(treatment, control, alpha=0.05):
    """Read out a completed holdout. Lists of realized per-sample incremental PROFIT ($). Welch test."""
    t, c = list(treatment), list(control)
    if len(t) < 2 or len(c) < 2:
        return {"note": "need >=2 samples per arm"}
    mt, mc, vt, vc = _mean(t), _mean(c), _var(t), _var(c)
    se = math.sqrt(vt / len(t) + vc / len(c))
    lift = mt - mc
    if se == 0:
        return {"lift": round(lift, 2), "note": "zero variance"}
    z = lift / se
    half = _z(1 - alpha / 2) * se
    p = 2 * (1 - _norm_cdf(abs(z)))
    return {"n_treatment": len(t), "n_control": len(c), "mean_treatment": round(mt, 2),
            "mean_control": round(mc, 2), "lift": round(lift, 2),
            "ci_low": round(lift - half, 2), "ci_high": round(lift + half, 2),
            "z": round(z, 2), "p_value": round(p, 4), "significant": bool(p < alpha),
            "note": "positive, CI excluding 0 => engine picks beat status quo on incremental profit."}


def bootstrap_ci(values, stat_fn, n_boot=2000, alpha=0.05, seed=0):
    """Percentile bootstrap CI for any statistic over `values`. Deterministic given seed."""
    import random
    rng = random.Random(seed)
    n = len(values)
    if n < 3:
        return (None, None)
    stats = []
    for _ in range(n_boot):
        s = [values[rng.randrange(n)] for _ in range(n)]
        try:
            stats.append(stat_fn(s))
        except Exception:
            continue
    if not stats:
        return (None, None)
    stats.sort()
    return (round(stats[int((alpha / 2) * len(stats))], 3),
            round(stats[int((1 - alpha / 2) * len(stats)) - 1], 3))


# --- small self-contained stats (no scipy in the hot path) ---
def _mean(x): return sum(x) / len(x)
def _var(x):
    m = _mean(x)
    return sum((v - m) ** 2 for v in x) / (len(x) - 1)
def _norm_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _z(p):
    """Inverse standard-normal CDF (Acklam's approximation)."""
    if not 0 < p < 1:
        raise ValueError("p in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
