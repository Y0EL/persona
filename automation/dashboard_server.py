"""
Dashboard FastAPI server untuk monitor automation lamaran kerja live.

Run:
    python dashboard_server.py
    # atau auto-spawn dari main.py
"""
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import dashboard_parsers as P


HERE = Path(__file__).parent
STATIC_DIR = HERE / "dashboard_static"
SCREENSHOT_FILE = STATIC_DIR / "current.png"
RUN_LOG = HERE / "run.log"
PROFILE_PATH = Path(r"C:\Users\Engineer02\Desktop\persona\profile\yoel_profile.json")

# Cap default — kalau main.py expose ini, bisa override via /api/stats
DEFAULT_CAP = 20

# Cache untuk markdown parse (invalidate via mtime)
_report_cache = {"mtime": 0, "data": None}


def _today_report_path() -> str:
    return P.get_today_report_path(config.REPORT_DIR)


def _get_report() -> dict:
    """Cached parse of today report; invalidate by mtime."""
    path = _today_report_path()
    if not os.path.exists(path):
        return {"date": "", "total_in_header": 0, "applies": [], "retrospectives": []}
    mtime = os.path.getmtime(path)
    if _report_cache["data"] is not None and _report_cache["mtime"] == mtime:
        return _report_cache["data"]
    data = P.parse_today_report(path)
    _report_cache["mtime"] = mtime
    _report_cache["data"] = data
    return data


app = FastAPI(title="Persona Apply Dashboard")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ====================== ENDPOINTS ======================

@app.get("/")
async def root():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return HTMLResponse("<h1>Dashboard not built yet</h1><p>dashboard_static/index.html missing.</p>")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "ts": int(time.time())}


@app.get("/api/profile")
async def api_profile():
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return {
        "full_name": "Yoel Andreas Manoppo",
        "headline": "AI Forward Deployed Engineer",
        "location": "Jakarta, Indonesia",
    }


@app.get("/api/stats")
async def api_stats():
    report = _get_report()
    state = P.parse_state(config.STATE_FILE)
    session = P.parse_session_state(str(RUN_LOG))

    per_platform = P.per_platform_count(report["applies"])

    # Caps per platform — default DEFAULT_CAP for all
    caps = {p: DEFAULT_CAP for p in P.PLATFORMS}

    # Mark which platforms are TAMAT (from log)
    done_platforms = {d["platform"]: d["applied"] for d in session.get("platforms_done", [])}

    return {
        "today": {
            "total": report["total_in_header"] or len(report["applies"]),
            "date": report["date"],
            "per_platform": per_platform,
            "caps": caps,
            "platforms_done": done_platforms,
        },
        "all_time": {
            "total_applied": len(state.get("applied_jobs", [])),
        },
        "session": {
            "started_at": session.get("started_at", ""),
            "current_platform": session.get("current_platform", ""),
            "current_batch": session.get("current_batch", 0),
            "current_total": session.get("current_total", 0),
            "platform_cap": session.get("platform_cap", DEFAULT_CAP),
            "last_action": session.get("last_action", ""),
            "log_size": session.get("log_size", 0),
        },
    }


@app.get("/api/applies")
async def api_applies(limit: int = 50):
    report = _get_report()
    return {"items": report["applies"][:limit], "total": len(report["applies"])}


@app.get("/api/retrospectives")
async def api_retrospectives():
    report = _get_report()
    return {"items": report["retrospectives"]}


@app.get("/api/current")
async def api_current():
    session = P.parse_session_state(str(RUN_LOG))
    tail = P.tail_lines(str(RUN_LOG), n=10)
    return {
        "platform": session.get("current_platform", ""),
        "batch": session.get("current_batch", 0),
        "total": session.get("current_total", 0),
        "cap": session.get("platform_cap", DEFAULT_CAP),
        "last_action": session.get("last_action", ""),
        "tail": tail,
        "screenshot": None,
    }


@app.get("/api/log/tail")
async def api_log_tail(n: int = 50):
    return {"lines": P.tail_lines(str(RUN_LOG), n=n)}


# ====================== HISTORY ENDPOINTS ======================

@app.get("/api/history/days")
async def api_history_days():
    """List semua file laporan harian dengan metadata ringkas."""
    return {"items": P.list_report_files(config.REPORT_DIR)}


@app.get("/api/history/day/{ddmmyyyy}")
async def api_history_day(ddmmyyyy: str):
    """Full parsed report untuk satu hari (DDMMYYYY)."""
    path = os.path.join(config.REPORT_DIR, ddmmyyyy + ".md")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found", "ddmmyyyy": ddmmyyyy}, status_code=404)
    data = P.parse_today_report(path)
    # juga return raw markdown untuk download / inspect
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_md = f.read()
    except Exception:
        raw_md = ""
    return {
        "ddmmyyyy": ddmmyyyy,
        "date": data["date"],
        "total": len(data["applies"]),
        "applies": data["applies"],
        "retrospectives": data["retrospectives"],
        "per_platform": P.per_platform_count(data["applies"]),
        "raw_md": raw_md,
    }


@app.get("/api/history/heatmap")
async def api_history_heatmap(days: int = 14):
    """Heatmap data 7×24 atau 14×24 — day × hour."""
    return P.heatmap_data(config.REPORT_DIR, days=max(1, min(days, 60)))


@app.get("/api/history/range")
async def api_history_range(from_date: str, to_date: str,
                              hour_from: int = 0, hour_to: int = 23):
    """Filtered applies dalam rentang tanggal + jam."""
    items = P.applies_in_range(config.REPORT_DIR, from_date, to_date, hour_from, hour_to)
    # Aggregate stats
    by_platform = {}
    by_date = {}
    for a in items:
        p = a.get("platform", "?")
        by_platform[p] = by_platform.get(p, 0) + 1
        d = a.get("iso_date", "?")
        by_date[d] = by_date.get(d, 0) + 1
    return {
        "total": len(items),
        "items": items,
        "by_platform": by_platform,
        "by_date": by_date,
    }


@app.get("/api/log/stream")
async def api_log_stream(request: Request):
    """SSE stream of new log lines."""
    tailer = P.tail_generator(str(RUN_LOG))

    async def event_gen():
        # Send initial tail
        initial = P.tail_lines(str(RUN_LOG), n=30)
        for ln in initial:
            yield {"event": "log", "data": ln}

        while True:
            if await request.is_disconnected():
                break
            new_lines = tailer.read_new()
            for ln in new_lines:
                yield {"event": "log", "data": ln}
            await asyncio.sleep(1.0)

    return EventSourceResponse(event_gen())


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("DASHBOARD_PORT", "8000"))
    print(f"[dashboard] http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
