import sys
import os
import time
import uiautomator2

sys.path.insert(0, os.path.dirname(__file__))

import config
import state_manager
import glints
import jobstreet
import adb_utils


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


def main():
    mode = "both"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("js", "jobstreet", "jobs"):
            mode = "jobstreet"
        elif arg in ("g", "glints"):
            mode = "glints"

    print("=" * 48)
    print("[main] AUTO APPLY — START")
    if mode == "jobstreet":
        print(f"[main] Mode: JOBSTREET-ONLY (batch={config.BATCH_SIZE})")
    elif mode == "glints":
        print(f"[main] Mode: GLINTS-ONLY (batch={config.BATCH_SIZE})")
    else:
        print(f"[main] Pola: {config.BATCH_SIZE}G -> {config.BATCH_SIZE}JS bergantian")
    print("=" * 48)

    d = connect()

    if mode != "glints" and not state_manager.jobstreet_logged_in():
        jobstreet.login_with_google(d)

    total_g  = 0
    total_js = 0
    round_n  = 0
    zero_rounds = 0

    while True:
        round_n += 1
        print(f"\n[main] --- Round {round_n} ---")

        g = 0
        if mode != "jobstreet":
            print(f"[main] Giliran GLINTS (maks {config.BATCH_SIZE})")
            try:
                g = glints.run_batch(d, limit=config.BATCH_SIZE)
            except Exception as e:
                print(f"[main] Glints crash: {e}")
            total_g += g

        j = 0
        if mode != "glints":
            print(f"[main] Giliran JOBSTREET (maks {config.BATCH_SIZE})")
            try:
                j = jobstreet.run_batch(d, limit=config.BATCH_SIZE)
            except Exception as e:
                print(f"[main] JobStreet crash: {e}")
            total_js += j

        print(f"[main] Round {round_n} selesai — G:{g} JS:{j} | Total G:{total_g} JS:{total_js}")

        if g == 0 and j == 0:
            zero_rounds += 1
            if zero_rounds >= 5:
                print("[main] Stop: 5 round berturut tidak ada lamaran baru")
                print("[main] Coba lagi besok — lowongan baru akan muncul di feed")
                break
        else:
            zero_rounds = 0

    print("\n" + "=" * 48)
    print(f"[main] SELESAI — Glints {total_g} | JobStreet {total_js} | Total {total_g+total_js}")
    print(f"[main] Laporan: {config.REPORT_DIR}")
    print("=" * 48)


if __name__ == "__main__":
    main()
