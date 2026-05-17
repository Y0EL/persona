"""
HITL Watcher Daemon untuk automation lamaran kerja.

Tugas:
  1. Tail file log automation tiap N detik
  2. Screenshot device tiap M detik
  3. Deteksi stuck state (layar sama berturut-turut, log gak update)
  4. Hitung apply rate (lamaran per menit)
  5. Auto-recover: kalau stuck >X menit, kill + restart main.py
  6. Print update real time pakai loguru biar gampang dibaca

Usage:
    python watcher.py                       # auto recover on stuck
    python watcher.py --no-recover          # cuma report, gak restart
    python watcher.py --log run.log         # path log custom
"""
import os
import re
import sys
import time
import hashlib
import subprocess
import argparse
import threading
from datetime import datetime

from loguru import logger

sys.path.insert(0, os.path.dirname(__file__))
import config


logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss}</green> "
        "<level>{level: <8}</level> "
        "<cyan>{extra[ctx]: <8}</cyan> "
        "<level>{message}</level>"
    ),
    colorize=True,
    level="DEBUG",
)
logger.configure(extra={"ctx": "system"})


ADB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
DEVICE   = config.DEVICE_SERIAL
SCREEN_PATH = os.path.join(os.path.dirname(__file__), "watch_screen.png")


def adb(*args, timeout=10):
    try:
        out = subprocess.check_output(
            [ADB_PATH, "-s", DEVICE, *args],
            stderr=subprocess.STDOUT, timeout=timeout,
        )
        return out.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERR: {e}"


def current_pkg():
    out = adb("shell", "dumpsys", "window", "windows")
    m = re.search(r"mCurrentFocus=Window\{[^}]*\s+(\S+?)/(\S+?)\}", out)
    if m:
        return m.group(1), m.group(2)
    return ("", "")


def screen_signature():
    """Hash dari content-desc + text pertama di layar (proxy buat 'layar sama')."""
    try:
        adb("shell", "uiautomator", "dump", "/sdcard/w.xml")
        out = adb("shell", "cat", "/sdcard/w.xml")
        texts = re.findall(r'(?:text|content-desc)="([^"]{4,40})"', out)
        # Pakai 25 string pertama biar sensitif tapi tidak terlalu sensitive
        sig = "|".join(sorted(set(texts))[:25])
        return hashlib.md5(sig.encode()).hexdigest()[:10]
    except Exception:
        return None


def save_screen():
    adb("shell", "screencap", "-p", "/sdcard/w.png")
    adb("pull", "/sdcard/w.png", SCREEN_PATH)


def count_reports(report_path):
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            txt = f.read()
        return len(re.findall(r"^## \d+\.", txt, re.MULTILINE))
    except Exception:
        return 0


def python_pids():
    try:
        out = subprocess.check_output(
            ["powershell", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            timeout=10,
        )
        return [int(x) for x in out.decode().strip().split() if x.strip().isdigit()]
    except Exception:
        return []


def is_main_running(log_path):
    """Cek apakah main.py jalan: ada python process + log file di-update <30s lalu."""
    if not python_pids():
        return False
    if not os.path.exists(log_path):
        return False
    age = time.time() - os.path.getmtime(log_path)
    return age < 60


def kill_python():
    subprocess.run(
        ["powershell", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force"],
        timeout=10,
    )


def restart_automation(log_path, mode):
    """Spawn ulang main.py di background, log ke file."""
    kill_python()
    time.sleep(2)
    # Force stop apps
    adb("shell", "am", "force-stop", "com.jobstreet.jobstreet")
    adb("shell", "am", "force-stop", "com.glints.candidate")
    time.sleep(1)

    here = os.path.dirname(__file__)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = ["python", "-u", "main.py"]
    if mode and mode != "both":
        cmd.append(mode)

    log_f = open(log_path, "a", encoding="utf-8")
    log_f.write(f"\n\n=== RESTART by watcher @ {datetime.now().isoformat(timespec='seconds')} ===\n\n")
    log_f.flush()
    subprocess.Popen(
        cmd, cwd=here, env=env,
        stdout=log_f, stderr=subprocess.STDOUT,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default=os.path.join(os.path.dirname(__file__), "run.log"))
    p.add_argument("--mode", default="both", choices=["both", "glints", "jobstreet"])
    p.add_argument("--interval", type=int, default=30, help="detik antar check")
    p.add_argument("--stuck-threshold", type=int, default=180, help="detik sebelum dianggap stuck")
    p.add_argument("--no-recover", action="store_true", help="tidak auto restart")
    p.add_argument("--once", action="store_true", help="cek sekali saja lalu exit")
    args = p.parse_args()

    log_path = args.log
    report_path = os.path.join(config.REPORT_DIR, datetime.now().strftime("%d%m%Y") + ".md")

    logger.bind(ctx="boot").info("Watcher daemon start")
    logger.bind(ctx="boot").info(f"log     = {log_path}")
    logger.bind(ctx="boot").info(f"report  = {report_path}")
    logger.bind(ctx="boot").info(f"mode    = {args.mode}")
    logger.bind(ctx="boot").info(f"interval= {args.interval}s  stuck={args.stuck_threshold}s")
    logger.bind(ctx="boot").info(f"recover = {not args.no_recover}")

    last_sig = None
    last_sig_change = time.time()
    last_log_size = 0
    last_log_change = time.time()
    last_count = count_reports(report_path)
    start_count = last_count
    start_time = time.time()

    iteration = 0
    while True:
        iteration += 1
        now = time.time()

        # 1. Cek python process + log freshness
        running = is_main_running(log_path)
        pids = python_pids()
        pkg, act = current_pkg()

        # 2. Cek log update
        if os.path.exists(log_path):
            sz = os.path.getsize(log_path)
            if sz != last_log_size:
                last_log_size = sz
                last_log_change = now
            log_age = int(now - last_log_change)
        else:
            log_age = 9999

        # 3. Cek screen signature
        sig = screen_signature()
        if sig and sig != last_sig:
            last_sig = sig
            last_sig_change = now
        screen_age = int(now - last_sig_change)

        # 4. Hitung report progress
        cur_count = count_reports(report_path)
        delta = cur_count - last_count
        last_count = cur_count
        elapsed_min = max((now - start_time) / 60.0, 0.01)
        rate = (cur_count - start_count) / elapsed_min

        # 5. Tail log 3 baris terakhir buat context
        last_log_lines = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            last_log_lines = [ln.strip() for ln in lines[-3:] if ln.strip()]
        except Exception:
            pass

        # === REPORT ===
        ctx_log = logger.bind(ctx="check")
        if running:
            ctx_log.success(f"running pid={pids[0] if pids else '?'} | pkg={pkg.split('.')[-1] if pkg else '?'}")
        else:
            ctx_log.warning(f"NOT RUNNING | pkg={pkg}")

        logger.bind(ctx="metric").info(
            f"reports={cur_count} (+{delta} this tick) | rate={rate:.2f}/min | sig={sig} screen_age={screen_age}s | log_age={log_age}s"
        )

        for ln in last_log_lines:
            logger.bind(ctx="taillog").debug(ln[:120])

        # === STUCK DETECTION ===
        is_stuck = False
        reason = ""
        if not running and not args.no_recover:
            is_stuck = True
            reason = "main.py tidak jalan"
        elif log_age > args.stuck_threshold:
            is_stuck = True
            reason = f"log gak update {log_age}s"
        elif screen_age > args.stuck_threshold and pkg in ("com.jobstreet.jobstreet", "com.glints.candidate"):
            is_stuck = True
            reason = f"layar sama {screen_age}s"

        if is_stuck:
            logger.bind(ctx="stuck").error(f"STUCK terdeteksi: {reason}")
            if not args.no_recover:
                logger.bind(ctx="recover").warning("Auto restart main.py...")
                restart_automation(log_path, args.mode)
                # Reset counters
                last_sig = None
                last_sig_change = time.time()
                last_log_size = 0
                last_log_change = time.time()
                time.sleep(5)  # kasih waktu boot

        if args.once:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
