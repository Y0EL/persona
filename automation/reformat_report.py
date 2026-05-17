"""
Reformat laporan lama (format plain text) jadi format MD yang rapi.
Parse setiap blok 'Platform...Catatan...', tulis ulang via report._build_entry.
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import report as r
from config import REPORT_DIR

_RE_SAL = re.compile(
    r"(?:mulai\s+)?(\d{6,})(?:\s+hingga\s+(\d{6,}))?"
)


def _parse_salary(text):
    text = (text or "").strip()
    if not text or text.startswith("tidak"):
        return None, None
    m = _RE_SAL.match(text)
    if not m:
        return None, None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return lo, hi


def _parse_old_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Skip header lama (2 baris pertama biasanya 'Laporan...' + 'Tanggal...')
    lines = text.splitlines()
    blocks = []
    cur = None
    for line in lines:
        if line.startswith("Platform "):
            if cur:
                blocks.append(cur)
            cur = {"platform": line[len("Platform "):].strip(), "fields": {}, "extra_lines": []}
            cur["current_key"] = "platform"
        elif cur is None:
            continue
        else:
            for key in ("Perusahaan ", "Posisi ", "Gaji ", "Deskripsi ", "Catatan "):
                if line.startswith(key):
                    k = key.strip().lower()
                    val = line[len(key):].strip()
                    cur["fields"][k] = val
                    cur["current_key"] = k
                    break
            else:
                # Lanjutan baris sebelumnya (mis. deskripsi multi-line)
                if cur and line.strip():
                    last = cur.get("current_key")
                    if last and last not in ("platform",):
                        cur["fields"][last] = (cur["fields"].get(last, "") + "\n" + line).strip()
    if cur:
        blocks.append(cur)
    return blocks


def reformat(path):
    blocks = _parse_old_file(path)
    if not blocks:
        print(f"[reformat] {path}: 0 blok, skip")
        return

    fname = os.path.basename(path)
    total = len(blocks)
    out = [r._file_header(fname, total)]

    for i, b in enumerate(blocks, 1):
        platform = b.get("platform", "Glints")
        fields = b["fields"]
        company = fields.get("perusahaan", "tidak diketahui")
        posisi = fields.get("posisi", "")
        gaji_text = fields.get("gaji", "")
        smin, smax = _parse_salary(gaji_text)
        deskripsi = fields.get("deskripsi", "")
        catatan = fields.get("catatan", "")
        entry = r._build_entry(i, platform, company, posisi, smin, smax, catatan, deskripsi)
        out.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print(f"[reformat] {path}: {total} entry direformat")


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        os.path.join(REPORT_DIR, f)
        for f in os.listdir(REPORT_DIR)
        if f.endswith(".md")
    ]
    for t in targets:
        if os.path.exists(t):
            reformat(t)
        else:
            print(f"[reformat] not found: {t}")
