from __future__ import annotations

from typing import Any


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    n = int(period)
    if n <= 0:
        raise ValueError("CRYPTO_PERIOD")
    acc = 0.0
    for i, value in enumerate(values):
        acc += value
        if i >= n:
            acc -= values[i - n]
        if i + 1 < n:
            out.append(None)
        else:
            out.append(acc / n)
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    n = int(period)
    if n <= 0:
        raise ValueError("CRYPTO_PERIOD")
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    n = int(period)
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, n + 1):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / n
    avg_loss = losses / n
    if avg_loss == 0:
        out[n] = 100.0
    else:
        out[n] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(n + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (n - 1) + gain) / n
        avg_loss = (avg_loss * (n - 1) + loss) / n
        if avg_loss == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
    k_smooth: int = 3,
) -> list[float | None]:
    n = int(period)
    raw: list[float | None] = []
    for i, close in enumerate(closes):
        if i + 1 < n:
            raw.append(None)
            continue
        window_h = highs[i + 1 - n : i + 1]
        window_l = lows[i + 1 - n : i + 1]
        hi = max(window_h)
        lo = min(window_l)
        if hi == lo:
            raw.append(50.0)
        else:
            raw.append(100.0 * (close - lo) / (hi - lo))
    filled = [0.0 if x is None else x for x in raw]
    smooth = sma(filled, k_smooth)
    out: list[float | None] = []
    for i, value in enumerate(smooth):
        if raw[i] is None or value is None:
            out.append(None)
        else:
            out.append(value)
    return out


def stoch_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14) -> list[float | None]:
    series = rsi(closes, rsi_period)
    numeric = [x if x is not None else 50.0 for x in series]
    dummy = numeric[:]
    return stochastic(dummy, dummy, numeric, stoch_period, 3)


def macd(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast = ema(closes, 12)
    slow = ema(closes, 26)
    line: list[float | None] = []
    for a, b in zip(fast, slow):
        if a is None or b is None:
            line.append(None)
        else:
            line.append(a - b)
    numeric = [0.0 if x is None else x for x in line]
    signal = ema(numeric, 9)
    hist: list[float | None] = []
    for a, b in zip(line, signal):
        if a is None or b is None:
            hist.append(None)
        else:
            hist.append(a - b)
    return line, signal, hist


def bollinger(
    closes: list[float], period: int = 20, width: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    mid = sma(closes, period)
    upper: list[float | None] = []
    lower: list[float | None] = []
    n = int(period)
    for i, mean in enumerate(mid):
        if mean is None:
            upper.append(None)
            lower.append(None)
            continue
        window = closes[i + 1 - n : i + 1]
        var = sum((x - mean) ** 2 for x in window) / n
        std = var ** 0.5
        upper.append(mean + width * std)
        lower.append(mean - width * std)
    return upper, mid, lower


def last(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def last2(values: list[float | None]) -> tuple[float | None, float | None]:
    found: list[float] = []
    for value in reversed(values):
        if value is not None:
            found.append(value)
        if len(found) == 2:
            break
    if len(found) == 0:
        return None, None
    if len(found) == 1:
        return found[0], None
    return found[0], found[1]


def evaluate(highs: list[float], lows: list[float], closes: list[float]) -> dict[str, Any]:
    if len(closes) < 60 or len(highs) != len(closes) or len(lows) != len(closes):
        raise ValueError("CRYPTO_CANDLES")
    rsi14 = last(rsi(closes, 14))
    stochs = {}
    oversold = 0
    overbought = 0
    for period in (5, 14, 21, 55):
        k = last(stochastic(highs, lows, closes, period, 3))
        stochs["stoch_" + str(period)] = k
        if k is not None and k <= 20:
            oversold += 1
        if k is not None and k >= 80:
            overbought += 1
    srsi = last(stoch_rsi(closes))
    macd_line, macd_sig, macd_hist = macd(closes)
    hist_now, hist_prev = last2(macd_hist)
    upper, mid, lower = bollinger(closes)
    close = closes[-1]
    band_u = last(upper)
    band_l = last(lower)
    buy_votes = 0
    sell_votes = 0
    notes: list[str] = []
    if rsi14 is not None and rsi14 <= 30:
        buy_votes += 1
        notes.append("RSI oversold")
    if rsi14 is not None and rsi14 >= 70:
        sell_votes += 1
        notes.append("RSI overbought")
    if oversold >= 3:
        buy_votes += 1
        notes.append("3/4 stoch oversold")
    if overbought >= 3:
        sell_votes += 1
        notes.append("3/4 stoch overbought")
    if srsi is not None and srsi <= 20:
        buy_votes += 1
        notes.append("StochRSI oversold")
    if srsi is not None and srsi >= 80:
        sell_votes += 1
        notes.append("StochRSI overbought")
    if hist_now is not None and hist_prev is not None and hist_prev <= 0 < hist_now:
        buy_votes += 1
        notes.append("MACD hist up")
    if hist_now is not None and hist_prev is not None and hist_prev >= 0 > hist_now:
        sell_votes += 1
        notes.append("MACD hist down")
    if band_l is not None and close <= band_l:
        buy_votes += 1
        notes.append("close <= lower BB")
    if band_u is not None and close >= band_u:
        sell_votes += 1
        notes.append("close >= upper BB")
    side = "none"
    if buy_votes >= 4 and buy_votes > sell_votes:
        side = "buy"
    elif sell_votes >= 4 and sell_votes > buy_votes:
        side = "sell"
    return {
        "close": close,
        "rsi14": rsi14,
        "stoch": stochs,
        "stoch_rsi": srsi,
        "macd_hist": hist_now,
        "bb_upper": band_u,
        "bb_lower": band_l,
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "notes": notes,
        "super": side,
        "source": "ohlcv",
    }
