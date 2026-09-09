"""Paper volatility state: GARCH(1,1) plus a two-state HMM.

Price direction is treated as noisy.  Position size follows the vol regime.
This module never places orders and has no network or wallet path.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA = "gg.crypto.vol-regime.v1"
GARCH_ALPHA = 0.08
GARCH_BETA = 0.90
MIN_BARS = 48
SIZE_FLOOR = 0.15
SIZE_CAP = 1.50
HMM_STAY_LOW = 0.90
HMM_STAY_HIGH = 0.80


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    previous = 0.0
    for raw in closes:
        price = _finite(raw, 0.0)
        if price <= 0:
            continue
        if previous > 0:
            out.append(math.log(price / previous))
        previous = price
    return out


def garch_1_1(returns: list[float]) -> dict[str, Any]:
    """Variance-targeted GARCH(1,1) with fixed persistence."""
    sample = [value for value in returns if math.isfinite(value)]
    if len(sample) < 8:
        return {
            "ok": False,
            "sigma": [],
            "last_sigma": 0.0,
            "unconditional": 0.0,
            "alpha": GARCH_ALPHA,
            "beta": GARCH_BETA,
        }
    mean = sum(sample) / len(sample)
    var = sum((value - mean) ** 2 for value in sample) / len(sample)
    var = max(var, 1e-12)
    persistence = GARCH_ALPHA + GARCH_BETA
    omega = var * max(1e-6, 1.0 - persistence)
    sigma2 = var
    series: list[float] = []
    for value in sample:
        sigma2 = omega + GARCH_ALPHA * (value * value) + GARCH_BETA * sigma2
        sigma2 = max(sigma2, 1e-12)
        series.append(math.sqrt(sigma2))
    return {
        "ok": True,
        "sigma": series,
        "last_sigma": series[-1],
        "unconditional": math.sqrt(var),
        "alpha": GARCH_ALPHA,
        "beta": GARCH_BETA,
        "omega": omega,
        "persistence": persistence,
    }


def hmm_two_state(returns: list[float]) -> dict[str, Any]:
    """Two-state HMM on absolute returns: LOW vs HIGH vol.

    Emissions are treated as exponential magnitudes.  A short EM pass
    estimates the two means; Viterbi then labels each bar.
    """
    magnitudes = [abs(value) for value in returns if math.isfinite(value)]
    if len(magnitudes) < 16:
        return {
            "ok": False,
            "states": [],
            "last_state": "UNKNOWN",
            "p_high": 0.5,
            "cluster_accuracy": 0.0,
        }
    ordered = sorted(magnitudes)
    low_mean = max(1e-8, ordered[len(ordered) // 3])
    high_mean = max(low_mean * 1.5, ordered[(2 * len(ordered)) // 3])
    for _ in range(4):
        low_sum = 0.0
        high_sum = 0.0
        low_n = 0
        high_n = 0
        for value in magnitudes:
            d_low = abs(value - low_mean)
            d_high = abs(value - high_mean)
            if d_low <= d_high:
                low_sum += value
                low_n += 1
            else:
                high_sum += value
                high_n += 1
        if low_n:
            low_mean = max(1e-8, low_sum / low_n)
        if high_n:
            high_mean = max(low_mean * 1.2, high_sum / high_n)

    def emit(state: str, value: float) -> float:
        mean = low_mean if state == "LOW" else high_mean
        return math.exp(-value / mean) / mean

    states: list[str] = []
    prev = "LOW"
    high_hits = 0
    for value in magnitudes:
        stay = HMM_STAY_LOW if prev == "LOW" else HMM_STAY_HIGH
        switch = 1.0 - stay
        p_keep = stay * emit(prev, value)
        other = "HIGH" if prev == "LOW" else "LOW"
        p_switch = switch * emit(other, value)
        current = prev if p_keep >= p_switch else other
        states.append(current)
        if current == "HIGH":
            high_hits += 1
        prev = current

    last = states[-1]
    # Persistence check used as a cheap clustering score, not a live edge claim.
    same = 0
    for index in range(1, len(states)):
        if states[index] == states[index - 1]:
            same += 1
    cluster = same / max(1, len(states) - 1)
    return {
        "ok": True,
        "states": states,
        "last_state": last,
        "p_high": high_hits / len(states),
        "low_mean": low_mean,
        "high_mean": high_mean,
        "cluster_accuracy": round(cluster, 4),
    }


def size_scale(
    last_sigma: float,
    unconditional: float,
    regime: str,
) -> float:
    """Vol-aware size.  High-vol regimes shrink; low-vol may use full size."""
    baseline = max(1e-8, _finite(unconditional, 0.0))
    sigma = max(1e-8, _finite(last_sigma, baseline))
    scale = baseline / sigma
    if str(regime or "").upper() == "HIGH":
        scale *= 0.50
    elif str(regime or "").upper() == "LOW":
        scale *= 1.00
    else:
        scale *= 0.75
    return max(SIZE_FLOOR, min(SIZE_CAP, scale))


def snapshot(closes: list[float]) -> dict[str, Any]:
    returns = log_returns(closes)
    garch = garch_1_1(returns)
    hmm = hmm_two_state(returns)
    scale = 0.0
    if garch.get("ok"):
        scale = size_scale(
            float(garch.get("last_sigma") or 0.0),
            float(garch.get("unconditional") or 0.0),
            str(hmm.get("last_state") or "UNKNOWN"),
        )
    return {
        "schema": SCHEMA,
        "ok": bool(garch.get("ok") and hmm.get("ok") and len(returns) >= MIN_BARS),
        "bars": len(returns),
        "garch": {
            "last_sigma": round(float(garch.get("last_sigma") or 0.0), 8),
            "unconditional": round(float(garch.get("unconditional") or 0.0), 8),
            "alpha": GARCH_ALPHA,
            "beta": GARCH_BETA,
        },
        "hmm": {
            "last_state": str(hmm.get("last_state") or "UNKNOWN"),
            "p_high": round(float(hmm.get("p_high") or 0.0), 4),
            "cluster_accuracy": float(hmm.get("cluster_accuracy") or 0.0),
        },
        "size_scale": round(scale, 4),
        "note": "Size follows vol regime. Direction is not treated as the edge.",
        "mode": "PAPER_ONLY",
    }
