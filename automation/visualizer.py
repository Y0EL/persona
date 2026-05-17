"""
Visualizer KOSMETIK untuk laporan lamaran kerja.
Baca file DDMMYYYY.md di folder Lamaran, lalu simulate scanning + display
seolah-olah backend worker lagi cari dan apply ke perusahaan secara live.

Pakai loguru biar terminal kelihatan professional dan keren.

Usage:
    python visualizer.py                  -> visualisasi file hari ini
    python visualizer.py 17052026.md      -> file spesifik
    python visualizer.py --fast           -> tanpa delay
"""
import os
import re
import sys
import time
import random
import shutil
from datetime import datetime

from loguru import logger

sys.path.insert(0, os.path.dirname(__file__))
from config import REPORT_DIR


logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss.SSS}</green> "
        "<level>{level: <8}</level> "
        "<cyan>{extra[ctx]: <14}</cyan> "
        "<level>{message}</level>"
    ),
    colorize=True,
    level="DEBUG",
)
logger.configure(extra={"ctx": "system"})


# Terminal width
TERM_W = shutil.get_terminal_size((100, 24)).columns
TERM_W = max(80, min(TERM_W, 120))

C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "red":    "\033[31m",
    "green":  "\033[32m",
    "yellow": "\033[33m",
    "blue":   "\033[34m",
    "purple": "\033[35m",
    "cyan":   "\033[36m",
    "white":  "\033[37m",
}


def _today_file():
    return datetime.now().strftime("%d%m%Y") + ".md"


def parse_report(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    entries = []
    blocks = re.split(r"^## \d+\.\s+", text, flags=re.MULTILINE)[1:]
    for blk in blocks:
        lines = blk.split("\n")
        company = lines[0].strip()
        entry = {"company": company}
        for ln in lines[1:30]:
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", ln)
            if m:
                key = m.group(1).strip().lower().replace(" ", "_")
                val = m.group(2).strip()
                if key not in ("field", "---"):
                    entry[key] = val
        desc_lines = [ln[2:].strip() for ln in lines if ln.startswith("> ")]
        entry["description"] = " ".join(desc_lines)[:200]
        note_lines = [ln[2:].strip() for ln in lines if ln.startswith("- ")]
        entry["catatan"] = note_lines
        entries.append(entry)
    return entries


def banner():
    c, b = C["cyan"], C["bold"]
    r = C["reset"]
    bar = "=" * (TERM_W - 4)
    print()
    print(f"  {c}+{bar}+{r}")
    print(f"  {c}|{r} {b}AUTO APPLY JOB SCANNER  v1.0{r}".ljust(TERM_W + 12) + f"{c}|{r}")
    print(f"  {c}|{r} {C['dim']}Backend worker replay simulation{r}".ljust(TERM_W + 12) + f"{c}|{r}")
    print(f"  {c}+{bar}+{r}")
    print()


def spinner_frame(i):
    frames = ["|", "/", "-", "\\"]
    return frames[i % len(frames)]


def render_progress(current, total, label="", width=40):
    if total <= 0:
        return
    pct = current / total
    fill = int(pct * width)
    bar = C["green"] + "#" * fill + C["dim"] + "." * (width - fill) + C["reset"]
    msg = f"  {C['bold']}[PROGRESS]{C['reset']} [{bar}] {C['yellow']}{current}/{total}{C['reset']} {C['dim']}{pct*100:5.1f}%{C['reset']} {label}"
    # Pad and overwrite
    pad = " " * max(0, TERM_W - 4 - len(re.sub(r'\033\[[0-9;]*m', '', msg)))
    sys.stdout.write("\r" + msg + pad)
    sys.stdout.flush()


def loading_dots(prefix_log, msg, duration=0.6, delay_per_dot=0.15):
    """Simulate dots loading: 'Searching .  .  .'"""
    dots = ["", " .", " . .", " . . ."]
    n = int(duration / delay_per_dot)
    for i in range(n):
        d = dots[i % len(dots)]
        sys.stdout.write(f"\r{C['dim']} {spinner_frame(i)} {msg}{d}{C['reset']}" + " " * 30)
        sys.stdout.flush()
        time.sleep(delay_per_dot)
    sys.stdout.write("\r" + " " * (TERM_W - 2) + "\r")
    sys.stdout.flush()
    prefix_log.info(msg)


def jitter(base):
    return base + random.uniform(-0.02, 0.04)


def visualize_entry(idx, total, e, fast=False):
    platform = e.get("platform", "Unknown")
    posisi = e.get("posisi", "Unknown")
    perusahaan = e.get("company", "Unknown")
    gaji = e.get("gaji", "tidak dicantumkan")
    waktu = e.get("waktu_lamar", "??:??")
    desc = e.get("description", "")

    color = C["blue"] if platform.lower() == "glints" else C["purple"]

    sys_log    = logger.bind(ctx="scanner")
    parse_log  = logger.bind(ctx="parser")
    filter_log = logger.bind(ctx="filter")
    apply_log  = logger.bind(ctx=f"apply.{platform[:3].lower()}")
    report_log = logger.bind(ctx="report")

    render_progress(idx - 1, total, f"{C['dim']}scanning feed...{C['reset']}")

    # Searching with spinner
    if not fast:
        loading_dots(sys_log, f"Scanning {platform} feed cards", duration=0.5)
    else:
        sys_log.debug(f"Scanning {platform} feed cards")

    sys_log.debug(f"Card found at index {idx}")
    if not fast:
        time.sleep(jitter(0.05))

    parse_log.info("Extracting card metadata")
    if not fast:
        time.sleep(jitter(0.08))
    parse_log.success(f"COMPANY  : {perusahaan}")
    if not fast:
        time.sleep(jitter(0.05))
    parse_log.success(f"POSITION : {posisi}")
    if not fast:
        time.sleep(jitter(0.05))
    parse_log.success(f"SALARY   : {gaji}")
    if not fast:
        time.sleep(jitter(0.1))

    render_progress(idx - 1, total, f"{C['dim']}validating filters...{C['reset']}")

    filter_log.info(f"Salary min check ({gaji})")
    if not fast:
        time.sleep(jitter(0.05))
    filter_log.info("Blacklist check [GSP, Zando, Eka, ADIDAYA]")
    if not fast:
        time.sleep(jitter(0.05))
    filter_log.info("Fuzzy keyword match against profile")
    if not fast:
        time.sleep(jitter(0.05))
    filter_log.info("Location check (Jabodetabek)")
    if not fast:
        time.sleep(jitter(0.05))
    filter_log.success("All checks PASSED")
    if not fast:
        time.sleep(jitter(0.1))

    render_progress(idx - 1, total, f"{C['dim']}opening detail page...{C['reset']}")

    if not fast:
        loading_dots(apply_log, "Opening job detail and tapping apply", duration=0.4)
    else:
        apply_log.info("Opening detail + apply")

    apply_log.info("Step 1/4 documents")
    if not fast:
        time.sleep(jitter(0.06))
    apply_log.info("Step 2/4 employer questions")
    if not fast:
        time.sleep(jitter(0.08))
    apply_log.info("Step 3/4 profile update")
    if not fast:
        time.sleep(jitter(0.06))
    apply_log.success("Step 4/4 SUBMIT")
    if not fast:
        time.sleep(jitter(0.08))

    report_log.success(f"Application sent @ {waktu}")
    if not fast:
        time.sleep(jitter(0.08))

    # Card box
    print()
    print(f"  {color}.{'-' * 50}.{C['reset']}")
    print(f"  {color}|{C['reset']} {C['bold']}{perusahaan[:48]:<48}{C['reset']} {color}|{C['reset']}")
    print(f"  {color}|{C['reset']} {posisi[:48]:<48} {color}|{C['reset']}")
    print(f"  {color}|{C['reset']} {gaji[:48]:<48} {color}|{C['reset']}")
    print(f"  {color}|{C['reset']} {C['dim']}{platform:<48}{C['reset']} {color}|{C['reset']}")
    print(f"  {color}'{'-' * 50}'{C['reset']}")
    print()

    render_progress(idx, total, f"{C['green']}applied -> {perusahaan[:24]}{C['reset']}")
    print()
    if not fast:
        time.sleep(jitter(0.18))


def summary_panel(entries):
    glints    = [e for e in entries if e.get("platform", "").lower() == "glints"]
    jobstreet = [e for e in entries if e.get("platform", "").lower() == "jobstreet"]

    c, r = C["cyan"], C["reset"]
    bar = "=" * (TERM_W - 4)
    print()
    print(f"  {c}+{bar}+{r}")
    print(f"  {c}|{r} {C['bold']}SCAN COMPLETE  Final Report{r}".ljust(TERM_W + 12) + f"{c}|{r}")
    print(f"  {c}+{bar}+{r}")
    print()

    print(f"  {C['yellow']}>>{r} {C['bold']}Total Lamaran{r}: {C['yellow']}{C['bold']}{len(entries)}{r}")
    print(f"  {C['blue']}>>{r} {C['bold']}Glints{r}:        {C['blue']}{len(glints)}{r}")
    print(f"  {C['purple']}>>{r} {C['bold']}JobStreet{r}:     {C['purple']}{len(jobstreet)}{r}")
    print()

    companies = {}
    for e in entries:
        cc = e.get("company", "")
        if cc and cc != "tidak diketahui":
            companies[cc] = companies.get(cc, 0) + 1
    top = sorted(companies.items(), key=lambda x: -x[1])[:5]
    if top and any(n > 1 for _, n in top):
        print(f"  {C['bold']}Perusahaan dengan lamaran terbanyak{r}:")
        for cname, n in top:
            if n < 2:
                continue
            print(f"  {C['cyan']}*{r} {cname} {C['dim']}({n}x){r}")
        print()

    positions = {}
    for e in entries:
        p = e.get("posisi", "")
        if p:
            positions[p] = positions.get(p, 0) + 1
    top_pos = sorted(positions.items(), key=lambda x: -x[1])[:8]
    if top_pos:
        print(f"  {C['bold']}Posisi paling banyak dilamar{r}:")
        max_n = max(n for _, n in top_pos)
        for p, n in top_pos:
            bar_len = int((n / max_n) * 28) if max_n else 0
            graph = C["green"] + "#" * bar_len + C["dim"] + "-" * (28 - bar_len) + r
            print(f"  {C['white']}{p[:32]:<32}{r} {graph} {C['yellow']}{n}{r}")
        print()
    print(f"  {c}+{bar}+{r}")
    print()


def main():
    args = sys.argv[1:]
    fast = "--fast" in args
    files = [a for a in args if not a.startswith("--")]

    fname = files[0] if files else _today_file()
    if not fname.endswith(".md"):
        fname += ".md"
    path = os.path.join(REPORT_DIR, fname) if not os.path.isabs(fname) else fname

    banner()
    sys_log = logger.bind(ctx="system")
    sys_log.info("Initializing job scan engine")
    if not fast:
        time.sleep(0.3)
    sys_log.info(f"Loading report -> {os.path.basename(path)}")
    if not fast:
        time.sleep(0.3)

    if not os.path.exists(path):
        sys_log.error(f"File tidak ditemukan: {path}")
        return

    entries = parse_report(path)
    if not entries:
        sys_log.warning("Tidak ada entry untuk divisualisasi")
        return

    sys_log.info("Connecting to ADB device 13344254B7000215")
    if not fast:
        time.sleep(0.25)
    sys_log.success("Connected -> S686LN-OP Android 35")
    if not fast:
        time.sleep(0.25)
    sys_log.info("Worker pool ready, starting scan")
    if not fast:
        time.sleep(0.4)
    print()

    for i, e in enumerate(entries, 1):
        visualize_entry(i, len(entries), e, fast=fast)

    summary_panel(entries)


if __name__ == "__main__":
    main()
