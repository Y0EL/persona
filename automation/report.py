import os
import re
from datetime import datetime
from config import REPORT_DIR

_MONTHS = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
           "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

# Karakter yang tidak boleh muncul di laporan (sesuai aturan format)
_STRIP = str.maketrans({
    "—": " ",  # em-dash
    "–": " ",  # en-dash
    "‒": " ",  # figure-dash
    "‐": " ",
    "‑": " ",
    "―": " ",
    ";": ",",
    "​": "",
    "’": "'",
    "“": '"',
    "”": '"',
    "•": "-",  # bullet -> hyphen
    "·": "-",  # middle dot
})


def _clean(text):
    if not text:
        return ""
    return text.translate(_STRIP).strip()


def _today_filename():
    return datetime.now().strftime("%d%m%Y") + ".md"


def _format_idr(value):
    """Format integer rupiah -> 'Rp 8.000.000'."""
    if not value:
        return ""
    s = f"{int(value):,}".replace(",", ".")
    return f"Rp {s}"


def _format_salary(salary_min, salary_max):
    if salary_min and salary_max and salary_min != salary_max:
        return f"{_format_idr(salary_min)} hingga {_format_idr(salary_max)}"
    if salary_min:
        return f"mulai {_format_idr(salary_min)}"
    if salary_max:
        return f"hingga {_format_idr(salary_max)}"
    return "tidak dicantumkan"


def _split_notes(notes_text):
    """Pecah catatan jadi list bullet (split by '|' atau newline)."""
    if not notes_text:
        return []
    parts = re.split(r"\s*\|\s*|\n", notes_text)
    items = []
    for p in parts:
        p = _clean(p)
        if p and len(p) > 1 and p not in items:
            items.append(p)
    return items[:20]


def _split_description(desc):
    """Pecah deskripsi jadi list paragraf bullet."""
    if not desc:
        return []
    parts = re.split(r"\n+|\.\s+(?=[A-Z])", desc)
    items = []
    for p in parts:
        p = _clean(p)
        if p and len(p) > 3:
            items.append(p[:200])
    return items[:8]


def _build_entry(idx, platform, company, position, salary_min, salary_max, notes, description, ai_summary=""):
    perusahaan = _clean(company) or "tidak diketahui"
    posisi = _clean(position)
    gaji = _format_salary(salary_min, salary_max)

    lines = [
        "",
        f"## {idx}. {perusahaan}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Platform | {_clean(platform)} |",
        f"| Posisi | {posisi} |",
        f"| Perusahaan | {perusahaan} |",
        f"| Gaji | {gaji} |",
        f"| Waktu Lamar | {datetime.now().strftime('%H:%M')} |",
        "",
    ]

    # Kalau ada AI summary, prefer pakai itu (lebih kontekstual + kultur perusahaan).
    if ai_summary and len(ai_summary) > 80:
        clean_ai = _clean(ai_summary)
        lines.append(clean_ai)
        lines.append("")
    else:
        # Fallback ke format lama: bullet description + catatan.
        desc_lines = _split_description(description)
        note_lines = _split_notes(notes)
        if desc_lines:
            lines.append("**Deskripsi Pekerjaan**")
            lines.append("")
            for d in desc_lines:
                lines.append(f"> {d}")
            lines.append("")
        if note_lines:
            lines.append("**Catatan**")
            lines.append("")
            for n in note_lines:
                lines.append(f"- {n}")
            lines.append("")

    lines.append("---")
    return "\n".join(lines) + "\n"


def _count_existing_entries(fpath):
    if not os.path.exists(fpath):
        return 0
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        return len(re.findall(r"^##\s+\d+\.", text, re.MULTILINE))
    except Exception:
        return 0


def _file_header(fname, total_so_far):
    dt = datetime.strptime(fname.replace(".md", ""), "%d%m%Y")
    return (
        "# Laporan Lamaran Kerja\n"
        "\n"
        f"**Tanggal:** {dt.day} {_MONTHS[dt.month]} {dt.year}  \n"
        f"**Total Lamaran:** {total_so_far}\n"
        "\n"
        "---\n"
    )


def _update_total_in_header(fpath, new_total):
    """Update baris 'Total Lamaran:' di header file."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        text = re.sub(
            r"(\*\*Total Lamaran:\*\*\s*)\d+",
            f"\\g<1>{new_total}",
            text,
            count=1,
        )
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def write_platform_done(platform, applied_count, retrospective_md):
    """
    Append section penutup untuk satu platform yang selesai.
    Format:
        ## [SELESAI] Platform <X> | <N> lowongan
        <AI retrospective markdown>
        ---
    """
    os.makedirs(REPORT_DIR, exist_ok=True)
    fname = _today_filename()
    fpath = os.path.join(REPORT_DIR, fname)

    body = (retrospective_md or "").strip()
    if not body:
        body = (
            f"_Tidak ada retrospective AI untuk {platform} kali ini._\n\n"
            f"Total lowongan ter-apply hari ini di {platform}: {applied_count}."
        )

    block = (
        "\n"
        f"## [SELESAI] Platform {_clean(platform)} | {applied_count} lowongan ter-apply hari ini\n"
        "\n"
        f"_Sesi {_clean(platform)} ditutup pada {datetime.now().strftime('%H:%M')}._\n"
        "\n"
        f"{body}\n"
        "\n"
        "---\n"
    )

    with open(fpath, "a", encoding="utf-8") as f:
        f.write(block)
    print(f"[report] {platform} SELESAI block written ({applied_count} apply)")


def write_application(platform, company, position, salary_min, salary_max, notes, description="", ai_summary=""):
    os.makedirs(REPORT_DIR, exist_ok=True)
    fname = _today_filename()
    fpath = os.path.join(REPORT_DIR, fname)

    existing = _count_existing_entries(fpath)
    next_idx = existing + 1

    entry = _build_entry(
        next_idx, platform, company, position,
        salary_min, salary_max, notes, description, ai_summary,
    )

    is_new = not os.path.exists(fpath) or os.path.getsize(fpath) == 0
    with open(fpath, "a", encoding="utf-8") as f:
        if is_new:
            f.write(_file_header(fname, next_idx))
        f.write(entry)

    if not is_new:
        _update_total_in_header(fpath, next_idx)

    print(f"[report] {platform} | {_clean(company)} | {_clean(position)}")
