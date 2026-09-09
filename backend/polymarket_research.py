"""Read-only Polymarket market research for the Crypto surface.

The desktop deliberately keeps this adapter separate from the Solana wallet
and trading code.  It does not contact the network at import time or while
the Crypto status rail is refreshing.  A user action starts one bounded
DuckDB query against one Pendulumflow V3 hourly Parquet file.

DuckDB is optional because the application should still start when the
analytical dependency is not installed.  In that case the UI exposes the
validated URL and SQL preview and explains how to enable the query runner.
"""

from __future__ import annotations

import importlib.util
import math
import re
import threading
import time
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Sequence


ARCHIVE_BASE = "https://archive.pendulumflow.com/v3"
ARCHIVE_HOST = "archive.pendulumflow.com"
REPO_URL = "https://github.com/warproxxx/poly_data"
SOURCE_LABEL = "PENDULUMFLOW V3 · REMOTE PARQUET · READ ONLY"
PRESETS = ("SUMMARY", "TRADES", "TOUCH", "SCAN")
MAX_ROWS = 240
MAX_SLUG_LENGTH = 160

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HOUR_RE = re.compile(r"^\d{1,2}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")

QueryExecutor = Callable[[str], tuple[Sequence[str], Sequence[Sequence[Any]]]]


class DuckDBUnavailable(RuntimeError):
    """Raised when the optional local analytical runner is absent."""


def _utc_defaults() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.date().isoformat(), f"{now.hour:02d}"


def _normalise_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not _DATE_RE.fullmatch(raw):
        raise ValueError("POLYMARKET_DATE")
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("POLYMARKET_DATE") from exc
    if parsed.isoformat() != raw:
        raise ValueError("POLYMARKET_DATE")
    return raw


def _normalise_hour(value: Any) -> str:
    raw = str(value or "").strip()
    if not _HOUR_RE.fullmatch(raw):
        raise ValueError("POLYMARKET_HOUR")
    hour = int(raw)
    if hour < 0 or hour > 23:
        raise ValueError("POLYMARKET_HOUR")
    return f"{hour:02d}"


def _normalise_slug(value: Any, *, required: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError("POLYMARKET_SLUG_REQUIRED")
        return ""
    if len(raw) > MAX_SLUG_LENGTH or not _SLUG_RE.fullmatch(raw):
        raise ValueError("POLYMARKET_SLUG")
    return raw


def normalise_query(
    preset: Any,
    query_date: Any,
    hour: Any,
    slug: Any = "",
) -> dict[str, str]:
    mode = str(preset or "").strip().upper()
    if mode not in PRESETS:
        raise ValueError("POLYMARKET_PRESET")
    day = _normalise_date(query_date)
    utc_hour = _normalise_hour(hour)
    market_slug = _normalise_slug(slug, required=mode == "TOUCH")
    return {
        "preset": mode,
        "date": day,
        "hour": utc_hour,
        "slug": market_slug,
    }


def archive_url(query_date: Any, hour: Any) -> str:
    day = _normalise_date(query_date)
    utc_hour = _normalise_hour(hour)
    return f"{ARCHIVE_BASE}/{day}/{utc_hour}/{day}T{utc_hour}.parquet"


def _sql_literal(value: str) -> str:
    """Quote an already validated value for a DuckDB SQL string literal."""

    return "'" + value.replace("'", "''") + "'"


def query_spec(
    preset: Any,
    query_date: Any,
    hour: Any,
    slug: Any = "",
) -> dict[str, str]:
    """Return the fixed, auditable query for a selected archive hour."""

    query = normalise_query(preset, query_date, hour, slug)
    url = archive_url(query["date"], query["hour"])
    source = _sql_literal(url)
    mode = query["preset"]
    if mode == "SUMMARY":
        sql = f"""
SELECT event_type, count(*) AS rows
FROM read_parquet({source})
GROUP BY 1
ORDER BY rows DESC
LIMIT 16
""".strip()
    elif mode == "TRADES":
        sql = f"""
SELECT strftime(timestamp_received, '%H:%M:%S') AS at,
       round(price, 4) AS price,
       round(size, 2) AS size,
       side,
       '0x' || lower(hex(market)) AS market
FROM read_parquet({source})
WHERE event_type = 'last_trade_price'
ORDER BY size DESC
LIMIT 20
""".strip()
    elif mode == "SCAN":
        sql = f"""
SELECT '0x' || lower(hex(market)) AS market,
       round(avg(best_ask - best_bid), 4) AS spread,
       round(avg(best_bid), 4) AS bid,
       round(avg(best_ask), 4) AS ask,
       count(*) AS quotes
FROM read_parquet({source})
WHERE event_type = 'best_bid_ask'
GROUP BY 1
HAVING spread IS NOT NULL
ORDER BY spread DESC
LIMIT 20
""".strip()
    else:
        market_slug = _sql_literal(query["slug"])
        sql = f"""
WITH target AS (
    SELECT market
    FROM read_parquet({source})
    WHERE event_type = 'new_market'
      AND slug = {market_slug}
    LIMIT 1
)
SELECT strftime(date_trunc('minute', timestamp_received), '%H:%M') AS minute,
       round(avg(best_bid), 4) AS bid,
       round(avg(best_ask), 4) AS ask
FROM read_parquet({source})
WHERE event_type = 'best_bid_ask'
  AND market = (SELECT market FROM target)
GROUP BY 1
ORDER BY 1
LIMIT 240
""".strip()
    return {
        **query,
        "url": url,
        "sql": sql,
        "source": SOURCE_LABEL,
    }


def duckdb_available() -> bool:
    try:
        return importlib.util.find_spec("duckdb") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _duckdb_execute(sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    if not duckdb_available():
        raise DuckDBUnavailable("DUCKDB_NOT_INSTALLED")
    import duckdb

    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute("SET TimeZone = 'UTC'")
        cursor = connection.execute(sql)
        columns = [str(item[0]) for item in (cursor.description or ())]
        rows = [tuple(row) for row in cursor.fetchmany(MAX_ROWS)]
        return columns, rows
    finally:
        connection.close()


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date_type)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _row_dicts(
    columns: Sequence[str], rows: Sequence[Sequence[Any]]
) -> list[dict[str, Any]]:
    names = [str(item) for item in columns]
    result: list[dict[str, Any]] = []
    for row in rows[:MAX_ROWS]:
        if isinstance(row, dict):
            result.append({str(key): _json_value(value) for key, value in row.items()})
            continue
        values = list(row)
        result.append(
            {
                name: _json_value(values[index]) if index < len(values) else None
                for index, name in enumerate(names)
            }
        )
    return result


def _display_market(value: Any) -> str:
    text = str(value or "")
    if len(text) > 22:
        return text[:10] + "…" + text[-8:]
    return text


def _format_lines(preset: str, rows: Sequence[dict[str, Any]]) -> list[str]:
    if preset == "SUMMARY":
        lines = ["EVENT TYPE                 ROWS"]
        for row in rows:
            lines.append(
                f"{str(row.get('event_type') or '')[:25]:<25} "
                f"{str(row.get('rows') or 0):>8}"
            )
        return lines
    if preset == "TRADES":
        lines = ["AT        PRICE      SIZE       SIDE  MARKET"]
        for row in rows:
            lines.append(
                f"{str(row.get('at') or '')[:8]:<8}  "
                f"{str(row.get('price') or '')[:10]:>10}  "
                f"{str(row.get('size') or '')[:10]:>10}  "
                f"{str(row.get('side') or '')[:4]:<4}  "
                f"{_display_market(row.get('market'))}"
            )
        return lines
    if preset == "SCAN":
        lines = ["MARKET              SPREAD      BID        ASK   QUOTES"]
        for row in rows:
            lines.append(
                f"{_display_market(row.get('market')):<18}  "
                f"{str(row.get('spread') or '')[:8]:>8}  "
                f"{str(row.get('bid') or '')[:8]:>8}  "
                f"{str(row.get('ask') or '')[:8]:>8}  "
                f"{str(row.get('quotes') or 0):>6}"
            )
        return lines
    lines = ["MINUTE    BID        ASK"]
    for row in rows:
        lines.append(
            f"{str(row.get('minute') or '')[:8]:<8}  "
            f"{str(row.get('bid') or '')[:10]:>10}  "
            f"{str(row.get('ask') or '')[:10]:>10}"
        )
    return lines


def _error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    if len(message) > 240:
        message = message[:237] + "..."
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def run_query(
    preset: Any,
    query_date: Any,
    hour: Any,
    slug: Any = "",
    *,
    executor: QueryExecutor | None = None,
) -> dict[str, Any]:
    """Run one fixed query, or return a precise local setup error."""

    started = time.monotonic()
    try:
        spec = query_spec(preset, query_date, hour, slug)
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "hint": "Choose a valid UTC date, hour and market slug.",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    try:
        columns, raw_rows = executor(spec["sql"]) if executor else _duckdb_execute(spec["sql"])
        rows = _row_dicts(columns, raw_rows)
        return {
            "ok": True,
            "error": "",
            "hint": "",
            "columns": [str(item) for item in columns],
            "rows": rows,
            "lines": _format_lines(spec["preset"], rows),
            "row_count": len(rows),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "sql": spec["sql"],
            "url": spec["url"],
        }
    except DuckDBUnavailable:
        return {
            "ok": False,
            "error": "DUCKDB_NOT_INSTALLED",
            "hint": "Install the optional Python package duckdb to run archive queries locally.",
            "columns": [],
            "rows": [],
            "lines": [],
            "row_count": 0,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "sql": spec["sql"],
            "url": spec["url"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "POLYMARKET_QUERY",
            "hint": _error_message(exc),
            "columns": [],
            "rows": [],
            "lines": [],
            "row_count": 0,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "sql": spec["sql"],
            "url": spec["url"],
        }


def _initial_state() -> dict[str, Any]:
    day, hour = _utc_defaults()
    return {
        "state": "idle",
        "preset": "SUMMARY",
        "date": day,
        "hour": hour,
        "slug": "",
        "source": SOURCE_LABEL,
        "url": "",
        "sql": "",
        "result": None,
        "error": "",
        "note": "Select one UTC archive hour. No query runs until RUN QUERY is pressed.",
    }


_lock = threading.RLock()
_state = _initial_state()
_generation = 0


def _snapshot_locked() -> dict[str, Any]:
    result = _state.get("result")
    if isinstance(result, dict):
        result = dict(result)
        result["rows"] = list(result.get("rows") or [])[:MAX_ROWS]
        result["lines"] = list(result.get("lines") or [])[:MAX_ROWS + 1]
    return {
        "state": str(_state.get("state") or "idle"),
        "preset": str(_state.get("preset") or "SUMMARY"),
        "date": str(_state.get("date") or ""),
        "hour": str(_state.get("hour") or ""),
        "slug": str(_state.get("slug") or ""),
        "source": SOURCE_LABEL,
        "url": str(_state.get("url") or ""),
        "sql": str(_state.get("sql") or ""),
        "result": result,
        "error": str(_state.get("error") or ""),
        "note": str(_state.get("note") or ""),
        "duckdb": duckdb_available(),
        "poly_data": {
            "repo": REPO_URL,
            "state": "OPTIONAL · NOT STARTED",
            "note": (
                "poly_data sync needs its own Envio HYPERSYNC_API and is never "
                "started by this read-only panel."
            ),
        },
    }


def snapshot() -> dict[str, Any]:
    with _lock:
        return _snapshot_locked()


def _run_async(
    token: int,
    spec: dict[str, str],
    executor: QueryExecutor | None,
) -> None:
    result = run_query(
        spec["preset"],
        spec["date"],
        spec["hour"],
        spec["slug"],
        executor=executor,
    )
    with _lock:
        if token != _generation:
            return
        _state["result"] = result
        _state["state"] = "done" if result.get("ok") else "error"
        _state["error"] = str(result.get("error") or "")
        _state["note"] = (
            "Query complete. Results are observational only."
            if result.get("ok")
            else str(result.get("hint") or "Query could not run.")
        )


def start_query(
    preset: Any,
    query_date: Any,
    hour: Any,
    slug: Any = "",
    *,
    executor: QueryExecutor | None = None,
) -> dict[str, Any]:
    """Start a single bounded query after validating all user inputs."""

    global _generation, _state
    try:
        spec = query_spec(preset, query_date, hour, slug)
    except ValueError as exc:
        with _lock:
            _generation += 1
            _state = _initial_state()
            _state.update(
                {
                    "state": "error",
                    "preset": str(preset or "").strip().upper(),
                    "date": str(query_date or "").strip(),
                    "hour": str(hour or "").strip(),
                    "slug": str(slug or "").strip(),
                    "error": str(exc),
                    "note": "Choose a valid UTC date, hour and market slug.",
                }
            )
            return _snapshot_locked()
    with _lock:
        if _state.get("state") == "running":
            return _snapshot_locked()
        _generation += 1
        token = _generation
        _state = _initial_state()
        _state.update(
            {
                "state": "running",
                **spec,
                "result": None,
                "error": "",
                "note": "Reading only the selected UTC archive hour…",
            }
        )
        thread = threading.Thread(
            target=_run_async,
            args=(token, spec, executor),
            name="gg-polymarket-query",
            daemon=True,
        )
        thread.start()
        return _snapshot_locked()


def reset() -> dict[str, Any]:
    global _generation, _state
    with _lock:
        _generation += 1
        _state = _initial_state()
        return _snapshot_locked()


def reset_for_tests() -> None:
    reset()
