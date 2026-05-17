import subprocess
import time
import os

ADB_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Android", "Sdk", "platform-tools", "adb.exe"
)


def adb(serial, *args, timeout=15):
    cmd = [ADB_PATH, "-s", serial] + list(str(a) for a in args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        print(f"[adb] Error: {e}")
        return ""


def launch_app(serial, package, activity, wait=5):
    adb(serial, "shell", "am", "force-stop", package)
    time.sleep(1)
    out = adb(serial, "shell", "am", "start", "-n", activity)
    time.sleep(wait)
    return out


def get_screen_text(serial):
    return adb(serial, "shell", "uiautomator", "dump", "/dev/stdout")


def is_app_foreground(serial, package):
    out = adb(serial, "shell", "dumpsys", "activity", "activities")
    return package in out
