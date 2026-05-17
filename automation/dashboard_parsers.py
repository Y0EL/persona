"""
Parser helpers untuk dashboard.
Read-only access ke run.log, Lamaran/<today>.md, state.json.
"""
import os
import re
import json
from datetime import datetime
from typing import Optional


# ====================== REPORT PARSER ======================

_ENTRY_HEADER_RE = re.compile(r"^## (\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_RETRO_HEADER_RE = re.compile(r"^## \[SELESAI\]\s+Platform\s+(.+?)\s+\|\s+(\d+)\s+lowongan.*$", re.MULTILINE)
_TABLE_FIELD_RE = re.compile(r"\|\s*(\w[\w ]*?)\s*\|\s*(.+?)\s*\|")
_TITLE_DATE_RE = re.compile(r"\*\*Tanggal:\*\*\s+(\d{1,2})\s+(\w+)\s+(\d{4})")
_TOTAL_RE = re.compile(r"\*\*Total Lamaran:\*\*\s+(\d+)")
_RETRO_CLOSED_AT_RE = re.compile(r"_Sesi .+? ditutup pada\s+(\d{1,2}:\d{2})\._")


def _today_filename() -> str:
    return datetime.now().strftime("%d%m%Y") + ".md"


def get_today_report_path(report_dir: str) -> str:
    return os.path.join(report_dir, _today_filename())


def parse_today_report(path: str) -> dict:
    """
    Parse markdown report jadi struct:
      {
        date: "17 Mei 2026",
        total_in_header: 145,
        applies: [{idx, platform, company, position, salary, applied_at, ai_summary_md, raw_md}, ...],
        retrospectives: [{platform, applied_count, retrospective_md, closed_at, raw_md}, ...],
      }
    """
    if not os.path.exists(path):
        return {"date": "", "total_in_header": 0, "applies": [], "retrospectives": []}

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    date = ""
    m = _TITLE_DATE_RE.search(text)
    if m:
        date = f"{m.group(1)} {m.group(2)} {m.group(3)}"

    total_in_header = 0
    m = _TOTAL_RE.search(text)
    if m:
        total_in_header = int(m.group(1))

    # Find all section starts (apply entries + retrospectives)
    sections = []
    for m in re.finditer(r"^## (.+?)$", text, re.MULTILINE):
        sections.append((m.start(), m.group(1).strip()))
    sections.append((len(text), ""))  # sentinel

    applies = []
    retrospectives = []

    for i in range(len(sections) - 1):
        start = sections[i][0]
        header = sections[i][1]
        end = sections[i + 1][0]
        body = text[start:end]

        retro_m = _RETRO_HEADER_RE.match(f"## {header}")
        if retro_m:
            platform = retro_m.group(1).strip()
            applied_count = int(retro_m.group(2))
            closed_m = _RETRO_CLOSED_AT_RE.search(body)
            closed_at = closed_m.group(1) if closed_m else ""
            # Body without the header line + closed_at marker
            retro_md = re.sub(r"^## \[SELESAI\].*?\n", "", body, count=1).strip()
            retro_md = re.sub(r"_Sesi .+? ditutup pada \d{1,2}:\d{2}\._\n?", "", retro_md, count=1).strip()
            retro_md = retro_md.rstrip("-").rstrip().rstrip("---").strip()
            retrospectives.append({
                "platform": platform,
                "applied_count": applied_count,
                "retrospective_md": retro_md,
                "closed_at": closed_at,
                "raw_md": body.strip(),
            })
            continue

        entry_m = re.match(r"^(\d+)\.\s+(.+)$", header)
        if not entry_m:
            continue
        idx = int(entry_m.group(1))
        company_header = entry_m.group(2).strip()

        # Parse table
        fields = {}
        for fm in _TABLE_FIELD_RE.finditer(body):
            k = fm.group(1).strip().lower()
            v = fm.group(2).strip()
            if v in ("---", "Value", "Field"):
                continue
            fields[k] = v

        # AI summary: everything after table block, before final ---
        # Detect table end: after last "|" line, content begins.
        ai_summary = ""
        lines = body.split("\n")
        after_table = False
        ai_lines = []
        for ln in lines:
            if not after_table:
                if ln.strip().startswith("|") or ln.strip().startswith("**Tentang"):
                    after_table = True if ln.strip().startswith("**Tentang") else after_table
                    if ln.strip().startswith("**Tentang"):
                        ai_lines.append(ln)
                continue
            if ln.strip() == "---":
                break
            ai_lines.append(ln)

        # Fallback: capture from first ** header to ---
        if not ai_lines:
            m2 = re.search(r"(\*\*Tentang.+?)(?=\n---)", body, re.DOTALL)
            if m2:
                ai_summary = m2.group(1).strip()
        else:
            ai_summary = "\n".join(ai_lines).strip()

        applies.append({
            "idx": idx,
            "platform": fields.get("platform", ""),
            "company": fields.get("perusahaan", company_header),
            "position": fields.get("posisi", ""),
            "salary": fields.get("gaji", ""),
            "applied_at": fields.get("waktu lamar", ""),
            "ai_summary_md": ai_summary,
            "raw_md": body.strip(),
        })

    # Reverse so newest first
    applies.sort(key=lambda x: x["idx"], reverse=True)
    retrospectives.sort(key=lambda x: x["closed_at"], reverse=True)

    return {
        "date": date,
        "total_in_header": total_in_header,
        "applies": applies,
        "retrospectives": retrospectives,
    }


# ====================== STATE PARSER ======================

def parse_state(state_path: str) -> dict:
    if not os.path.exists(state_path):
        return {"applied_jobs": [], "jobstreet_logged_in": False}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"applied_jobs": [], "jobstreet_logged_in": False}


# ====================== LOG / SESSION PARSER ======================

_PLATFORM_START_RE = re.compile(r"\[main\] >>> PLATFORM (\w+) START")
_PLATFORM_TAMAT_RE = re.compile(r"\[main\] <<< PLATFORM (\w+) TAMAT: (\d+) apply")
_BATCH_LINE_RE = re.compile(r"\[main\] (\w+) batch #(\d+) \(limit (\d+), total (\d+)/(\d+)\)")
_BATCH_RESULT_RE = re.compile(r"\[main\] (\w+) batch #(\d+): \+?(\d+) apply \(total (\d+)/(\d+)\)")
_RUN_START_RE = re.compile(r"=== .*START\s+(\d{1,2}:\d{2}:\d{2})\s*===")


def parse_session_state(log_path: str) -> dict:
    """
    Parse run.log untuk extract session state terkini.
    """
    state = {
        "started_at": "",
        "current_platform": "",
        "current_batch": 0,
        "current_total": 0,
        "platform_cap": 20,
        "last_action": "",
        "log_size": 0,
        "platforms_done": [],
    }
    if not os.path.exists(log_path):
        return state

    state["log_size"] = os.path.getsize(log_path)
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return state

    # Find last run start marker
    for ln in lines:
        m = _RUN_START_RE.search(ln)
        if m:
            state["started_at"] = m.group(1)

    # Find latest platform start
    for ln in reversed(lines):
        m = _PLATFORM_START_RE.search(ln)
        if m:
            state["current_platform"] = m.group(1).title()
            break

    # Find latest batch progress
    for ln in reversed(lines):
        m = _BATCH_LINE_RE.search(ln) or _BATCH_RESULT_RE.search(ln)
        if m:
            state["current_batch"] = int(m.group(2))
            state["current_total"] = int(m.group(4))
            state["platform_cap"] = int(m.group(5))
            break

    # Platforms already TAMAT
    for ln in lines:
        m = _PLATFORM_TAMAT_RE.search(ln)
        if m:
            state["platforms_done"].append({
                "platform": m.group(1).title(),
                "applied": int(m.group(2)),
            })

    # Last meaningful action: latest non-empty line
    for ln in reversed(lines):
        s = ln.strip()
        if not s:
            continue
        state["last_action"] = s[:200]
        break

    return state


def tail_lines(log_path: str, n: int = 30) -> list:
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[-n:]]
    except Exception:
        return []


def tail_generator(log_path: str, start_offset: Optional[int] = None):
    """
    Generator yang yield baris baru dari log_path.
    Caller: gunakan dengan asyncio.sleep di SSE endpoint.
    """
    if start_offset is None:
        start_offset = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    return _TailState(log_path, start_offset)


class _TailState:
    def __init__(self, path: str, offset: int):
        self.path = path
        self.offset = offset
        self._buf = ""

    def read_new(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            sz = os.path.getsize(self.path)
            if sz < self.offset:
                # log rotated/truncated
                self.offset = 0
            if sz == self.offset:
                return []
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.offset)
                chunk = f.read()
                self.offset = f.tell()
        except Exception:
            return []
        self._buf += chunk
        if "\n" not in self._buf:
            return []
        parts = self._buf.split("\n")
        self._buf = parts[-1]
        return [p for p in parts[:-1] if p.strip()]


# ====================== PER-PLATFORM AGGREGATION ======================

PLATFORMS = ["Glints", "JobStreet", "LinkedIn", "Indeed"]


def per_platform_count(applies: list) -> dict:
    counts = {p: 0 for p in PLATFORMS}
    for a in applies:
        p = a.get("platform", "")
        if p in counts:
            counts[p] += 1
        else:
            counts[p] = counts.get(p, 0) + 1
    return counts


# ====================== HISTORY ======================

import glob

_DDMMYYYY_RE = re.compile(r"^(\d{2})(\d{2})(\d{4})\.md$", re.IGNORECASE)


def _ddmmyyyy_to_iso(s: str) -> str:
    m = _DDMMYYYY_RE.match(s + (".md" if not s.endswith(".md") else ""))
    if not m:
        return ""
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return f"{yyyy}-{mm}-{dd}"


def _iso_to_ddmmyyyy(iso: str) -> str:
    """2026-05-17 -> 17052026"""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%d%m%Y")
    except Exception:
        return ""


def list_report_files(report_dir: str) -> list:
    """
    List semua DDMMYYYY.md di Lamaran/.
    Return [{ddmmyyyy, iso_date, day_label, total, per_platform, mtime, has_retro}]
    sorted newest first.
    """
    if not os.path.isdir(report_dir):
        return []
    items = []
    for path in glob.glob(os.path.join(report_dir, "*.md")):
        fname = os.path.basename(path)
        m = _DDMMYYYY_RE.match(fname)
        if not m:
            continue
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        iso = f"{yyyy}-{mm}-{dd}"
        ddmmyyyy = f"{dd}{mm}{yyyy}"
        try:
            data = parse_today_report(path)
            total = len(data["applies"])
            ppc = per_platform_count(data["applies"])
            has_retro = len(data["retrospectives"]) > 0
            try:
                d_obj = datetime.strptime(iso, "%Y-%m-%d")
                day_label = d_obj.strftime("%d %b %Y")
                weekday = d_obj.strftime("%a")
            except Exception:
                day_label = iso
                weekday = ""
            items.append({
                "ddmmyyyy": ddmmyyyy,
                "iso_date": iso,
                "day_label": day_label,
                "weekday": weekday,
                "total": total,
                "per_platform": ppc,
                "mtime": os.path.getmtime(path),
                "has_retro": has_retro,
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["iso_date"], reverse=True)
    return items


def heatmap_data(report_dir: str, days: int = 14) -> dict:
    """
    Build hourly heatmap untuk N hari terakhir.
    Return {
       dates: [iso_date, ...] (oldest -> newest, len=days),
       day_labels: [str],
       weekday: [str],
       grid: { iso_date: { hour_0_23: count } },
       max_count: int,
       totals: { iso_date: total },
       platforms: { iso_date: {Glints:N, ...} },
    }
    """
    today = datetime.now().date()
    dates = []
    for i in range(days - 1, -1, -1):
        from datetime import timedelta
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))

    grid = {iso: {h: 0 for h in range(24)} for iso in dates}
    totals = {iso: 0 for iso in dates}
    platforms = {iso: {p: 0 for p in PLATFORMS} for iso in dates}

    files = list_report_files(report_dir)
    files_by_iso = {f["iso_date"]: f for f in files}

    for iso in dates:
        info = files_by_iso.get(iso)
        if not info:
            continue
        path = os.path.join(report_dir, info["ddmmyyyy"] + ".md")
        data = parse_today_report(path)
        for a in data["applies"]:
            t = a.get("applied_at", "")
            hm = re.match(r"^(\d{1,2}):(\d{2})$", t)
            if not hm:
                continue
            h = int(hm.group(1))
            if 0 <= h <= 23:
                grid[iso][h] += 1
        totals[iso] = info["total"]
        platforms[iso] = info["per_platform"]

    max_count = 0
    for iso in dates:
        for h in range(24):
            if grid[iso][h] > max_count:
                max_count = grid[iso][h]

    day_labels = []
    weekdays = []
    for iso in dates:
        try:
            d_obj = datetime.strptime(iso, "%Y-%m-%d")
            day_labels.append(d_obj.strftime("%d %b"))
            weekdays.append(d_obj.strftime("%a"))
        except Exception:
            day_labels.append(iso)
            weekdays.append("")

    return {
        "dates": dates,
        "day_labels": day_labels,
        "weekdays": weekdays,
        "grid": grid,
        "max_count": max_count,
        "totals": totals,
        "platforms": platforms,
    }


def applies_in_range(report_dir: str, from_iso: str, to_iso: str,
                       hour_from: int = 0, hour_to: int = 23) -> list:
    """Return list of applies dalam rentang [from_iso..to_iso] dan jam [hour_from..hour_to]."""
    try:
        d_from = datetime.strptime(from_iso, "%Y-%m-%d").date()
        d_to   = datetime.strptime(to_iso,   "%Y-%m-%d").date()
    except Exception:
        return []
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    if hour_from > hour_to:
        hour_from, hour_to = hour_to, hour_from

    out = []
    files = list_report_files(report_dir)
    for f in files:
        try:
            d_f = datetime.strptime(f["iso_date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d_f < d_from or d_f > d_to:
            continue
        path = os.path.join(report_dir, f["ddmmyyyy"] + ".md")
        data = parse_today_report(path)
        for a in data["applies"]:
            t = a.get("applied_at", "")
            hm = re.match(r"^(\d{1,2}):(\d{2})$", t)
            if not hm:
                continue
            h = int(hm.group(1))
            if h < hour_from or h > hour_to:
                continue
            a2 = dict(a)
            a2["iso_date"] = f["iso_date"]
            a2["day_label"] = f["day_label"]
            out.append(a2)
    out.sort(key=lambda x: (x["iso_date"], x.get("applied_at", "")), reverse=True)
    return out
