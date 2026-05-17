import sys
import os
import time
import subprocess
import uiautomator2

sys.path.insert(0, os.path.dirname(__file__))

import config
import state_manager
import glints
import jobstreet
import linkedin
import indeed
import adb_utils
import report
import ai_helper


def _spawn_dashboard():
    """Spawn dashboard_server.py in background. Non-blocking — failure is silent."""
    if "--no-dashboard" in sys.argv:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    server_py = os.path.join(here, "dashboard_server.py")
    if not os.path.exists(server_py):
        print("[main] dashboard_server.py not found, skip")
        return None
    try:
        log_f = open(os.path.join(here, "dashboard.log"), "a", encoding="utf-8")
        flags = 0
        if sys.platform == "win32":
            # CREATE_NO_WINDOW = subprocess tanpa CMD window (silent background).
            # Tidak pakai DETACHED_PROCESS — itu yang bikin window kebuka di Windows tertentu.
            flags = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            [sys.executable, "-u", server_py],
            cwd=here, stdout=log_f, stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        print(f"[main] Dashboard spawned PID {proc.pid} -> http://127.0.0.1:8000")
        return proc
    except Exception as e:
        print(f"[main] Dashboard spawn gagal: {e}")
        return None


def connect():
    out = adb_utils.adb(config.DEVICE_SERIAL, "get-state")
    if "device" not in out:
        print("[main] HP tidak terdeteksi!")
        sys.exit(1)
    for i in range(3):
        try:
            d = uiautomator2.connect(config.DEVICE_SERIAL)
            info = d.info
            print(f"[main] Terhubung: {info.get('productName')} Android {info.get('sdkInt')}")
            return d
        except Exception as e:
            print(f"[main] Coba {i+1}/3: {e}")
            time.sleep(1)
    print("[main] Gagal konek.")
    sys.exit(1)


# Threshold zero-batch berturut sebelum platform dianggap "tamat".
MAX_ZERO_PER_PLATFORM = 2
# Cap maksimum apply per platform per sesi — supaya semua 4 platform tercoba hari ini,
# bukan Glints monopoli karena feed-nya paling kaya.
MAX_APPLY_PER_PLATFORM = 20


def run_platform_until_done(d, name, run_batch_fn, get_stats_fn=None, reset_stats_fn=None):
    """
    Jalankan platform `name` sampai zero apply MAX_ZERO_PER_PLATFORM kali berturut,
    ATAU total apply mencapai MAX_APPLY_PER_PLATFORM.
    Setelah tamat: panggil AI untuk retrospective + tulis ke report.
    Return total apply.
    """
    if reset_stats_fn:
        try:
            reset_stats_fn()
        except Exception:
            pass

    total = 0
    zero_streak = 0
    batch_n = 0
    print(f"\n{'='*48}\n[main] >>> PLATFORM {name.upper()} START (cap {MAX_APPLY_PER_PLATFORM})\n{'='*48}")

    while zero_streak < MAX_ZERO_PER_PLATFORM and total < MAX_APPLY_PER_PLATFORM:
        batch_n += 1
        remaining = MAX_APPLY_PER_PLATFORM - total
        batch_limit = min(config.BATCH_SIZE, remaining)
        print(f"\n[main] {name} batch #{batch_n} (limit {batch_limit}, total {total}/{MAX_APPLY_PER_PLATFORM})")
        try:
            count = run_batch_fn(d, limit=batch_limit)
        except Exception as e:
            print(f"[main] {name} crash: {e}")
            count = 0
        total += count
        if count == 0:
            zero_streak += 1
            print(f"[main] {name} batch #{batch_n}: 0 apply (zero_streak={zero_streak}/{MAX_ZERO_PER_PLATFORM})")
        else:
            zero_streak = 0
            print(f"[main] {name} batch #{batch_n}: +{count} apply (total {total}/{MAX_APPLY_PER_PLATFORM})")

    reason = "cap reached" if total >= MAX_APPLY_PER_PLATFORM else f"zero streak {zero_streak}"
    print(f"\n[main] <<< PLATFORM {name.upper()} TAMAT: {total} apply | {batch_n} batch | reason: {reason}\n")

    skip_counters, sample = ({}, [])
    if get_stats_fn:
        try:
            skip_counters, sample = get_stats_fn()
        except Exception:
            pass

    retro = ""
    try:
        retro = ai_helper.platform_retrospective(name, total, skip_counters, sample)
    except Exception as e:
        print(f"[main] AI retrospective {name} gagal: {e}")

    try:
        report.write_platform_done(name, total, retro)
    except Exception as e:
        print(f"[main] write_platform_done gagal: {e}")

    return total


def main():
    mode = "all"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("js", "jobstreet", "jobs"):
            mode = "jobstreet"
        elif arg in ("g", "glints"):
            mode = "glints"
        elif arg in ("li", "linkedin"):
            mode = "linkedin"
        elif arg in ("i", "indeed"):
            mode = "indeed"

    print("=" * 48)
    print("[main] AUTO APPLY - START (sequential mode)")
    print(f"[main] Mode: {mode.upper()} | batch={config.BATCH_SIZE} | max_zero={MAX_ZERO_PER_PLATFORM}")
    print("=" * 48)

    _spawn_dashboard()

    d = connect()

    do_glints    = mode in ("all", "glints")
    do_jobstreet = mode in ("all", "jobstreet")
    do_linkedin  = mode in ("all", "linkedin")
    do_indeed    = mode in ("all", "indeed")

    if do_jobstreet and not state_manager.jobstreet_logged_in():
        jobstreet.login_with_google(d)

    totals = {"Glints": 0, "JobStreet": 0, "LinkedIn": 0, "Indeed": 0}

    if do_glints:
        totals["Glints"] = run_platform_until_done(
            d, "Glints", glints.run_batch,
            getattr(glints, "get_session_stats", None),
            getattr(glints, "reset_session_stats", None),
        )

    if do_jobstreet:
        totals["JobStreet"] = run_platform_until_done(
            d, "JobStreet", jobstreet.run_batch,
            getattr(jobstreet, "get_session_stats", None),
            getattr(jobstreet, "reset_session_stats", None),
        )

    if do_linkedin:
        totals["LinkedIn"] = run_platform_until_done(
            d, "LinkedIn", linkedin.run_batch,
            getattr(linkedin, "get_session_stats", None),
            getattr(linkedin, "reset_session_stats", None),
        )

    if do_indeed:
        totals["Indeed"] = run_platform_until_done(
            d, "Indeed", indeed.run_batch,
            getattr(indeed, "get_session_stats", None),
            getattr(indeed, "reset_session_stats", None),
        )

    grand = sum(totals.values())
    print("\n" + "=" * 48)
    print(f"[main] ALL PLATFORMS TAMAT — total {grand} apply hari ini")
    for k, v in totals.items():
        print(f"[main]   {k}: {v}")
    print(f"[main] Laporan: {config.REPORT_DIR}")
    print("=" * 48)


if __name__ == "__main__":
    main()
