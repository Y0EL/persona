import re
import time
import state_manager
import report
import adb_utils
import ai_helper
from config import (
    DEVICE_SERIAL, GLINTS_PACKAGE, GLINTS_ACTIVITY,
    MIN_SALARY, BLACKLIST_COMPANIES, FUZZY_KEYWORDS,
    T_TAP, T_ANIM, T_LOAD, T_LAUNCH, BATCH_SIZE,
)

# Keywords yang akan di-search satu per satu di Glints.
# Setiap keyword bakal di-type ke search bar -> hasilkan cards yang di-filter via FUZZY_KEYWORDS.
SEARCH_KEYWORDS = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Agentic AI",
    "LLM Engineer",
    "Data Scientist",
    "Data Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Full Stack Developer",
    "Software Engineer",
    "Web Developer",
    "Python Developer",
    "Next JS Developer",
    "DevOps Engineer",
    "Cloud Engineer",
    "IT Support",
    "IT Specialist",
    "Blockchain Developer",
]

# Koordinat dari UI dump (tidak berubah karena layar 1080x2436)
SEARCH_ICON_X = 972   # center dari [864,150][1080,270]
SEARCH_ICON_Y = 210

_seen: set = set()
_keyword_idx = 0      # track keyword mana yang sedang diproses


def _launch_fresh():
    """Force stop dan launch untuk pastikan mulai dari home."""
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.3)
    adb_utils.adb(DEVICE_SERIAL, "shell", "am", "force-stop", GLINTS_PACKAGE)
    time.sleep(0.6)
    adb_utils.launch_app(DEVICE_SERIAL, GLINTS_PACKAGE, GLINTS_ACTIVITY, wait=T_LAUNCH)


def _ensure_home(d, max_attempts=6):
    """
    Pastikan kita di home Glints. Jika ada form/chat/detail terbuka,
    tutup paksa via tombol Tutup + dialog konfirmasi BATALKAN.
    """
    for _ in range(max_attempts):
        if _on_home(d):
            return True

        # Tutup form/chat via tombol X di kiri atas
        if d.xpath('//*[@content-desc="Tutup"]').wait(timeout=0.4):
            _click_node_by_coord(d, '//*[@content-desc="Tutup"]')
            time.sleep(T_ANIM + 0.2)
            # Dialog konfirmasi tutup. Glints punya 2 variasi label:
            #   "BATAL & JANGAN SIMPAN" (form lamaran)
            #   "BATALKAN LAMARAN" / "BATALKAN" (form syarat)
            for label in ["BATAL & JANGAN SIMPAN", "BATALKAN LAMARAN", "BATALKAN"]:
                if d.xpath(f'//*[contains(@content-desc,"{label}")]').wait(timeout=0.5):
                    _click_node_by_coord(d, f'//*[contains(@content-desc,"{label}")]')
                    time.sleep(T_ANIM)
                    break
            continue

        # Cek package — kalau bukan Glints, relaunch
        try:
            pkg = d.app_current().get("package", "")
        except Exception:
            pkg = ""
        if pkg != GLINTS_PACKAGE:
            _launch_fresh()
            time.sleep(T_ANIM)
            continue

        # Press back, lalu cek lagi
        d.press("back")
        time.sleep(T_TAP + 0.2)

    return _on_home(d)


def _tap_desc(d, keyword, timeout=2):
    """Tap elemen via content-desc (React Native)."""
    try:
        nodes = d.xpath(f'//*[contains(@content-desc,"{keyword}")]').all()
        if nodes:
            nodes[0].click()
            return True
    except Exception:
        pass
    return False


def _dismiss(d):
    """Dismiss popup yang mungkin muncul."""
    for kw in ["Nanti", "Skip", "Lewati", "Not Now", "Tutup", "Close"]:
        try:
            if d(text=kw).exists(timeout=0.4):
                d(text=kw).click()
                time.sleep(T_TAP)
                return
        except Exception:
            pass
    # Dismiss popup Preferensi (back)
    try:
        if d.xpath('//*[contains(@content-desc,"Preferensi")]').wait(timeout=0.3):
            d.press("back")
            time.sleep(T_TAP)
    except Exception:
        pass


def _on_home(d):
    """
    Cek apakah kita di home screen Glints.
    Indikator paling reliable: bottom nav tab 'Lowongan/Tab 1 dari 4' atau
    top tab 'For You/Tab 1 dari 4'.
    """
    try:
        if d.xpath('//*[contains(@content-desc,"Lowongan") and contains(@content-desc,"Tab 1 dari 4")]').wait(timeout=0.4):
            return True
        if d.xpath('//*[contains(@content-desc,"For You") and contains(@content-desc,"Tab 1 dari 4")]').wait(timeout=0.3):
            return True
    except Exception:
        pass
    return False


def _on_search_results(d, keyword):
    """Cek apakah kita di halaman hasil search untuk keyword ini."""
    try:
        nodes = d.xpath(f'//*[contains(@content-desc,"{keyword}")]').all()
        # Search bar ada di results page dengan content-desc = keyword
        for n in nodes:
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if m:
                y1, y2 = int(m.group(2)), int(m.group(4))
                if y1 < 400 and (y2 - y1) < 200:  # Search bar di atas
                    return True
    except Exception:
        pass
    return False


def _open_search(d, keyword):
    """
    Buka search Glints dan cari keyword.
    Flow: tap ikon search -> ketik keyword -> tekan ENTER.
    """
    # Tap ikon search di kanan atas
    d.click(SEARCH_ICON_X, SEARCH_ICON_Y)
    time.sleep(T_ANIM + 0.2)

    # Clear text via select-all + delete
    try:
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_DEL")
    except Exception:
        pass
    time.sleep(T_TAP)

    # Ketik keyword
    keyword_safe = keyword.replace(" ", "%s")
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", keyword_safe)
    time.sleep(T_ANIM)

    # Tekan ENTER untuk trigger search (lebih reliable dari tap suggestion)
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_ENTER")
    time.sleep(T_LOAD)

    # Verifikasi: layar hasil search punya search bar dengan keyword di atas
    # ATAU minimal nama keyword muncul di banyak card hasil.
    return _on_search_results(d, keyword)


def _ensure_on_results(d, keyword):
    """
    Pastikan kita ada di halaman search results untuk keyword ini.
    Jika tidak, navigate ke sana.
    """
    if _on_search_results(d, keyword):
        return True

    # Coba back dulu
    for _ in range(3):
        d.press("back")
        time.sleep(T_TAP)
        if _on_search_results(d, keyword):
            return True

    # Kembali ke home dan re-search
    pkg = d.app_current().get("package", "")
    if pkg != GLINTS_PACKAGE:
        _launch_fresh()
        _dismiss(d)
    else:
        # Press back sampai di home
        for _ in range(5):
            d.press("back")
            time.sleep(T_TAP)
            if _on_home(d):
                break

    return _open_search(d, keyword)


def _get_cards(d):
    """
    Ambil job cards dari halaman search results.
    Card = clickable View dengan content-desc panjang berisi \n.
    Filter: y > 414 untuk hindari header/search bar.
    """
    try:
        nodes = d.xpath('//*[@clickable="true" and @content-desc!=""]').all()
        result = []
        for n in nodes:
            desc = n.attrib.get("content-desc", "")
            if len(desc) < 40 or "\n" not in desc:
                continue
            bounds = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]", bounds)
            if m and int(m.group(2)) < 414:
                continue
            result.append((n, desc))
        return result
    except Exception:
        return []


def _parse_desc(desc):
    lines = [l.strip() for l in desc.split("\n") if l.strip()]
    # Hapus badge "BARU" / "SUDAH DILAMAR" dari awal jika ada
    if lines and lines[0] in ("BARU", "SUDAH DILAMAR", "HOT"):
        lines = lines[1:]
    position = lines[0] if lines else ""
    salary   = next((l for l in lines if re.search(r"Rp|jt|juta", l)), "")
    company  = ""
    for l in lines[1:5]:
        if any(p in l for p in ["PT ", "CV ", "Ltd", "Inc", "Corp", "Tbk", "Group", ".id"]):
            company = l
            break
    if not company:
        company = lines[2] if len(lines) > 2 else (lines[1] if len(lines) > 1 else "")
    return position, company, salary


def _parse_salary_range(text):
    if not text:
        return 0, 0
    nums = re.findall(r"\d+", text.replace(".", "").replace(",", ""))
    vals = []
    for n in nums:
        v = int(n)
        if "jt" in text.lower() or "juta" in text.lower():
            v *= 1_000_000
        elif v < 500:
            v *= 1_000_000
        if 1_000_000 <= v <= 300_000_000:
            vals.append(v)
    return (min(vals), max(vals)) if len(vals) >= 2 else (vals[0], vals[0]) if vals else (0, 0)


def _ok_salary(text):
    if not text:
        return True
    lo, hi = _parse_salary_range(text)
    return (lo == 0 and hi == 0) or hi >= MIN_SALARY or lo >= MIN_SALARY


def _blacklisted(company):
    return any(b.lower() in company.lower() for b in BLACKLIST_COMPANIES)


def _fuzzy(position):
    pl = position.lower()
    return any(k in pl for k in FUZZY_KEYWORDS)


def _already_applied_badge(desc):
    """Cek apakah card menampilkan badge 'SUDAH DILAMAR'."""
    return "SUDAH DILAMAR" in desc


def _extract_detail_texts(d):
    try:
        nodes = d.xpath('//*[@content-desc!=""]').all()
        texts = []
        for n in nodes:
            cd = n.attrib.get("content-desc", "")
            if len(cd) > 60 and "\n" in cd:
                texts.append(cd[:200])
        return " | ".join(texts[:2])[:300]
    except Exception:
        return ""


JABODETABEK = ["Jakarta", "Tangerang", "Depok", "Bekasi", "Bogor", "Banten"]


def _click_node_by_coord(d, xpath_expr):
    """
    Cari node via xpath, ambil bounds-nya, lalu click di tengahnya via koordinat.
    Lebih reliable dari node.click() untuk overlay/bottom sheet.
    """
    try:
        nodes = d.xpath(xpath_expr).all()
        if not nodes:
            return False
        b = nodes[0].attrib.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        if m:
            cx = (int(m.group(1)) + int(m.group(3))) // 2
            cy = (int(m.group(2)) + int(m.group(4))) // 2
            d.click(cx, cy)
            return True
    except Exception:
        pass
    return False


def _handle_syarat_dialog(d):
    """
    Handle popup 'Ada syarat yang tidak sesuai'.
    Muncul setelah tap CHAT UNTUK MELAMAR jika ada mismatch profil.
    - Jabodetabek: LANJUTKAN
    - Luar Jabodetabek: BATALKAN LAMARAN (return False)

    PENTING: Gunakan coordinate click via bounds, bukan node.click() —
    xpath click tidak reliable pada overlay/bottom sheet Glints.
    """
    try:
        if not d.xpath('//*[contains(@content-desc,"Ada syarat yang tidak sesuai")]').wait(timeout=1.5):
            return True  # Dialog tidak muncul

        # Baca lokasi dari dialog
        lokasi_nodes = d.xpath('//*[contains(@content-desc,"Lokasi Pekerjaan")]').all()
        lokasi_text = ""
        if lokasi_nodes:
            lokasi_text = lokasi_nodes[0].attrib.get("content-desc", "")

        if any(area in lokasi_text for area in JABODETABEK) or not lokasi_text:
            # Tap LANJUTKAN via koordinat dari bounds
            tapped = _click_node_by_coord(d, '//*[@content-desc="LANJUTKAN"]')
            if not tapped:
                # Fallback koordinat (bounds [48,2052][1032,2202])
                d.click(540, 2127)
            time.sleep(T_ANIM + 0.3)
            return True
        else:
            print(f"[glints] Lokasi di luar area: {lokasi_text} — batalkan")
            tapped = _click_node_by_coord(d, '//*[@content-desc="BATALKAN LAMARAN"]')
            if not tapped:
                d.click(540, 2277)
            time.sleep(T_ANIM)
            return False
    except Exception:
        return True


def _tap_apply_button(d):
    """
    Tap CHAT UNTUK MELAMAR / Lamar Tanpa CV.
    Glints React Native: tombol pakai content-desc, bukan text.

    Return:
      "ok"            -> tombol berhasil di-tap, form/dialog muncul
      "already"       -> job sudah pernah dilamar (skip)
      "no_button"     -> tidak ada tombol apply yang dikenali
    """
    # Cek dulu kalau sudah pernah dilamar
    if d.xpath('//*[contains(@content-desc,"Kamu telah melamar")]').wait(timeout=0.4):
        return "already"
    if d.xpath('//*[contains(@content-desc,"CHAT DENGAN HRD")]').wait(timeout=0.3):
        return "already"

    # Coba tombol apply utama (prefer CHAT UNTUK MELAMAR)
    tapped = False
    if _tap_desc(d, "CHAT UNTUK MELAMAR"):
        tapped = True
    elif _tap_desc(d, "Lamar Tanpa CV"):
        tapped = True
    else:
        # Last resort: koordinat sticky button bawah
        d.click(540, 2277)
        tapped = True

    time.sleep(T_ANIM)

    # Konfirmasi form/dialog muncul
    form_visible = bool(
        d.xpath('//*[contains(@content-desc,"SELANJUTNYA")]').wait(timeout=1.5) or
        d.xpath('//*[contains(@content-desc,"KIRIM")]').wait(timeout=1) or
        d.xpath('//*[contains(@content-desc,"Ada syarat")]').wait(timeout=1) or
        d.xpath('//*[@content-desc="Pertanyaan dari HRD"]').wait(timeout=1) or
        d.xpath('//*[@content-desc="Tutup"]').wait(timeout=0.6)
    )
    return "ok" if form_visible else "no_button"


def _sanitize_answer(text):
    """Bersihkan karakter yang bisa bikin ADB input crash."""
    text = text[:380]
    return (
        text.replace("\\", "")
            .replace('"', "'")
            .replace("`", "'")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("\t", " ")
            .replace("(", "")
            .replace(")", "")
            .replace("&", "and")
            .replace("|", "")
            .replace(";", ",")
            .replace("<", "")
            .replace(">", "")
            .replace("$", "")
            .replace("*", "")
            .replace("#", "")
            .replace("%", "")
    ).strip()


def _adb_type(text):
    """
    Ketik text via ADB input. Spasi diganti %s.
    Dipecah per ~80 char untuk hindari crash di string panjang.
    """
    safe = _sanitize_answer(text)
    if not safe:
        return
    words = safe.split(" ")
    chunks = []
    cur = []
    cur_len = 0
    for w in words:
        if cur_len + len(w) + 1 > 80 and cur:
            chunks.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
        else:
            cur.append(w)
            cur_len += len(w) + 1
    if cur:
        chunks.append(" ".join(cur))

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        if i > 0:
            adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", "%s")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", chunk.replace(" ", "%s"))


def _read_char_count(d):
    """
    Baca counter 'N/500' (atau /1000 dll) di dalam EditText.
    Return N (int) atau -1 kalau tidak ada.
    Denominator harus >= 50 untuk hindari step indicator '2/4'.
    """
    try:
        nodes = d.xpath('//*[@content-desc!=""]').all()
        for n in nodes:
            cd = n.attrib.get("content-desc", "").strip()
            m = re.match(r"^(\d+)\s*/\s*(\d+)$", cd)
            if m and int(m.group(2)) >= 50:
                return int(m.group(1))
    except Exception:
        pass
    return -1


def _find_question_text(d):
    """
    Cari pertanyaan yang berkaitan dengan EditText di layar Glints.
    Hanya pertimbangkan node di area form (y antara 300 dan 1800)
    dan dari package Glints — supaya notifikasi WhatsApp dll tidak ke-pickup.
    """
    try:
        nodes = d.xpath('//*[@content-desc!=""]').all()
        candidates = []
        for n in nodes:
            pkg = n.attrib.get("package", "")
            if pkg and pkg != GLINTS_PACKAGE:
                continue
            cd = n.attrib.get("content-desc", "").strip()
            if len(cd) < 20 or len(cd) > 400:
                continue
            low = cd.lower()
            # Skip tombol/label umum
            if any(skip in low for skip in [
                "selanjutnya", "kirim", "lanjutkan", "batalkan", "tutup", "kembali",
                "whatsapp", "notification", "pertanyaan dari hrd",
            ]):
                continue
            # Lokasi node — harus di area form
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            y1, y2 = int(m.group(2)), int(m.group(4))
            if y1 < 300 or y2 > 1900:
                continue
            # Pertanyaan: berakhir ? atau ada kata tanya
            is_q = "?" in cd or any(
                w in low for w in [
                    "berapa", "kenapa", "mengapa", "bagaimana", "apakah",
                    "how ", "why ", "what ", "describe", "explain", "tell us",
                    "ceritakan", "jelaskan", "alasan", "tahun ", "pengalaman",
                    "experience", "do you have", "are you",
                ]
            )
            if is_q:
                candidates.append((y1, cd))
        if not candidates:
            return ""
        candidates.sort()
        return candidates[0][1]
    except Exception:
        return ""


def _tap_all_clickable_by_desc(d, desc_value):
    """Tap SEMUA node clickable yang content-desc-nya sama persis (e.g. 'Mahir-Fasih')."""
    try:
        nodes = d.xpath(f'//*[@content-desc="{desc_value}" and @clickable="true"]').all()
        count = 0
        for n in nodes:
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            cx = (int(m.group(1)) + int(m.group(3))) // 2
            cy = (int(m.group(2)) + int(m.group(4))) // 2
            # Skip area tombol bottom (KEMBALI/SELANJUTNYA biasanya y>2100)
            if cy > 2100:
                continue
            d.click(cx, cy)
            time.sleep(T_TAP + 0.2)
            count += 1
        return count
    except Exception:
        return 0


def _handle_language_proficiency(d):
    """
    Step Glints: 'Seberapa mahir kamu dengan bahasa berikut'.
    Yoel: Indonesia (native), Inggris (C2), Mandarin (conversational).
    Pilih Mahir-Fasih untuk semua bahasa. Scroll bertahap untuk semua row.
    """
    try:
        if not d.xpath('//*[@content-desc="Mahir-Fasih" and @clickable="true"]').wait(timeout=0.4):
            return False

        for _ in range(3):
            d.swipe_ext("down", scale=0.5)
            time.sleep(T_TAP)

        tapped_ys = set()
        total = 0
        for _ in range(6):
            nodes = d.xpath('//*[@content-desc="Mahir-Fasih" and @clickable="true"]').all()
            new_taps = 0
            for n in nodes:
                b = n.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                if not m:
                    continue
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                if cy > 2100:
                    continue
                key = round(cy / 50) * 50
                if key in tapped_ys:
                    continue
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                d.click(cx, cy)
                time.sleep(T_TAP)
                tapped_ys.add(key)
                new_taps += 1
                total += 1
            sel = d.xpath('//*[contains(@content-desc,"SELANJUTNYA")]').all()
            for n in sel:
                if n.attrib.get("clickable", "false") == "true":
                    print(f"[glints]   bahasa: tap Mahir-Fasih x{total} (SELANJUTNYA aktif)")
                    return True
            if new_taps == 0:
                d.swipe_ext("up", scale=0.55)
                time.sleep(T_TAP + 0.1)
        print(f"[glints]   bahasa: tap Mahir-Fasih x{total}")
        return total > 0
    except Exception as e:
        print(f"[glints] _handle_language_proficiency error: {e}")
    return False


def _handle_skill_proficiency(d):
    """
    Step Glints: 'Seberapa mahir kamu dengan keahlian berikut'.
    Options: Tidak Berpengalaman / Dasar / Menengah / Ahli
    Yoel: Ahli di semua tech skill.

    Pakai skill_text+y-pos sebagai key supaya tidak tap dua kali (deselect radio).
    Scroll ke atas penuh dulu, baru scroll ke bawah bertahap.
    """
    try:
        if not d.xpath('//*[@content-desc="Ahli" and @clickable="true"]').wait(timeout=0.4):
            return False

        # Scroll ke paling atas form (banyak swipe down)
        for _ in range(8):
            d.swipe_ext("down", scale=0.7)
            time.sleep(0.08)

        tapped_keys = set()
        total = 0
        no_progress = 0
        for _ in range(20):
            nodes = d.xpath('//*[@content-desc="Ahli" and @clickable="true"]').all()
            new_taps = 0
            for n in nodes:
                b = n.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                if not m:
                    continue
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                if cy > 2100 or cy < 200:
                    continue
                # Granularity halus (20px) biar tiap row terdeteksi unik
                key = round(cy / 20) * 20
                if key in tapped_keys:
                    continue
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                d.click(cx, cy)
                time.sleep(0.18)
                tapped_keys.add(key)
                new_taps += 1
                total += 1
            # Stop kalau SELANJUTNYA sudah clickable
            for n in d.xpath('//*[contains(@content-desc,"SELANJUTNYA")]').all():
                if n.attrib.get("clickable", "false") == "true":
                    print(f"[glints]   skill: tap Ahli x{total} (SELANJUTNYA aktif)")
                    return True
            if new_taps == 0:
                no_progress += 1
                if no_progress >= 3:
                    break  # tidak ada Ahli baru meski sudah scroll, bailout
                d.swipe_ext("up", scale=0.7)
                time.sleep(0.15)
            else:
                no_progress = 0
                d.swipe_ext("up", scale=0.45)
                time.sleep(0.12)
        print(f"[glints]   skill: tap Ahli x{total}")
        return total > 0
    except Exception as e:
        print(f"[glints] _handle_skill_proficiency error: {e}")
    return False


def _handle_experience_years(d):
    """
    Step Glints: 'Berapa lama pengalaman yang Anda miliki'.
    Options: Tidak Berpengalaman / < 1 tahun / 1-3 thn / 3-5 tahun / 5-10 tahun / 10+ tahun

    Dua varian:
    1. Single question (1-2 row) -> pilih '1-3 thn' (Yoel 3 thn).
    2. Multi-industry matrix (3+ row) -> pilih 'Tidak Berpengalaman'
       untuk row industri non-tech (Construction, Distributor dll).
       Yoel hanya berpengalaman di software/tech.
    """
    try:
        if not d.xpath('//*[@content-desc="1-3 thn" and @clickable="true"]').wait(timeout=0.4):
            return False

        # Hitung jumlah row (= jumlah opsi 'Tidak Berpengalaman' clickable)
        zero_nodes = d.xpath('//*[@content-desc="Tidak Berpengalaman" and @clickable="true"]').all()
        n_rows = len(zero_nodes)

        if n_rows >= 2:
            # Multi-industry matrix: Yoel 0 yr di industri non-tech
            _scroll_to_top_of_form(d)
            tapped_keys = set()
            total = 0
            no_progress = 0
            for _ in range(20):
                nodes = d.xpath('//*[@content-desc="Tidak Berpengalaman" and @clickable="true"]').all()
                new_taps = 0
                for n in nodes:
                    b = n.attrib.get("bounds", "")
                    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                    if not m:
                        continue
                    cy = (int(m.group(2)) + int(m.group(4))) // 2
                    if cy > 2100 or cy < 200:
                        continue
                    key = round(cy / 20) * 20
                    if key in tapped_keys:
                        continue
                    cx = (int(m.group(1)) + int(m.group(3))) // 2
                    d.click(cx, cy)
                    time.sleep(0.18)
                    tapped_keys.add(key)
                    new_taps += 1
                    total += 1
                for n in d.xpath('//*[contains(@content-desc,"SELANJUTNYA")]').all():
                    if n.attrib.get("clickable", "false") == "true":
                        print(f"[glints]   industri: tap Tidak Berpengalaman x{total} (SELANJUTNYA aktif)")
                        return True
                if new_taps == 0:
                    no_progress += 1
                    if no_progress >= 3:
                        break
                    d.swipe_ext("up", scale=0.7)
                    time.sleep(0.15)
                else:
                    no_progress = 0
                    d.swipe_ext("up", scale=0.45)
                    time.sleep(0.12)
            print(f"[glints]   industri: tap Tidak Berpengalaman x{total}")
            return total > 0

        # Single question: Yoel 3 tahun -> 1-3 thn
        n = _tap_all_clickable_by_desc(d, "1-3 thn")
        if n > 0:
            print(f"[glints]   pengalaman: tap '1-3 thn' x{n}")
            return True
    except Exception as e:
        print(f"[glints] _handle_experience_years error: {e}")
    return False


def _scroll_to_top_of_form(d):
    """Scroll form ke paling atas via swipe down agresif."""
    for _ in range(8):
        d.swipe_ext("down", scale=0.7)
        time.sleep(0.08)


def _handle_yes_no_question(d):
    """
    Untuk pertanyaan ya/tidak (mis. 'Apakah kamu tinggal di Jakarta?').
    Default: pilih 'Ya' / 'Yes' (bersedia, mau, willing).
    Glints punya pasangan label campur: Ya+Tidak, Yes+No, atau Yes+Tidak.
    """
    try:
        has_yes = (
            d.xpath('//*[@content-desc="Ya" and @clickable="true"]').wait(timeout=0.3) or
            d.xpath('//*[@content-desc="Yes" and @clickable="true"]').wait(timeout=0.3)
        )
        has_no = (
            d.xpath('//*[@content-desc="Tidak" and @clickable="true"]').wait(timeout=0.3) or
            d.xpath('//*[@content-desc="No" and @clickable="true"]').wait(timeout=0.3)
        )
        if not (has_yes and has_no):
            return False

        # Tap semua "Ya" dan "Yes" yang clickable (untuk multi-row Yes/No questions)
        n_ya = _tap_all_clickable_by_desc(d, "Ya")
        n_yes = _tap_all_clickable_by_desc(d, "Yes")
        if n_ya + n_yes > 0:
            print(f"[glints]   ya/yes: tap {n_ya + n_yes}")
            return True
    except Exception:
        pass
    return False


def _handle_text_input(d):
    """
    Jika ada EditText di layar dan masih kosong, generate jawaban via AI dan isi.
    Return:
      "filled"  -> berhasil isi text (counter > 0)
      "skip"    -> sudah ada text sebelumnya / counter > 0
      "none"    -> tidak ada EditText
      "fail"    -> EditText ada tapi gagal isi (perlu bail out)
    """
    try:
        edits = d.xpath('//*[@class="android.widget.EditText"]').all()

        # Fallback: kalau class tidak match, deteksi via counter 'N/500' (text field
        # Glints kadang pakai BasicTextField / Compose). Cari clickable view di atas counter.
        if not edits:
            counter_nodes = []
            for n in d.xpath('//*[@content-desc!=""]').all():
                cd = n.attrib.get("content-desc", "").strip()
                m = re.match(r"^(\d+)\s*/\s*(\d+)$", cd)
                if m and int(m.group(2)) >= 50:
                    counter_nodes.append(n)
            if counter_nodes:
                # Anggap area di atas counter = input field. Buat pseudo-node.
                edits = counter_nodes  # akan dipakai untuk klik koordinat saja

        if not edits:
            return "none"

        existing = _read_char_count(d)
        if existing > 0:
            print(f"[glints] EditText sudah berisi {existing} char, skip.")
            return "skip"

        question = _find_question_text(d)
        if not question:
            question = "Tell us why you are a good fit for this role."

        print(f"[glints] EditText terdeteksi. Q: {question[:80]}")

        try:
            raw = ai_helper.answer_question(question, max_chars=380)
        except Exception as e:
            print(f"[glints] ai_helper error: {e}")
            raw = ai_helper._static_answer(question)

        answer = _sanitize_answer(raw)
        if not answer:
            answer = "I have strong relevant experience and am confident I can contribute effectively to this role."

        # Click EditText pertama via koordinat
        b = edits[0].attrib.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        cx = (int(m.group(1)) + int(m.group(3))) // 2 if m else 540
        cy = (int(m.group(2)) + int(m.group(4))) // 2 if m else 800
        d.click(cx, cy)
        time.sleep(T_TAP + 0.3)

        # Coba set_text via uiautomator2 dulu (paling reliable di EditText native)
        used_set_text = False
        try:
            d(className="android.widget.EditText").set_text(answer)
            used_set_text = True
            time.sleep(T_ANIM)
        except Exception as e:
            print(f"[glints] set_text gagal, fallback ADB input: {e}")

        # Verifikasi
        time.sleep(0.4)
        count = _read_char_count(d)

        if count <= 0 and not used_set_text:
            # Fallback ADB input text
            d.click(cx, cy)
            time.sleep(T_TAP)
            _adb_type(answer)
            time.sleep(T_ANIM)
            count = _read_char_count(d)

        if count <= 0:
            # Last resort: tap lagi + ADB input
            d.click(cx, cy)
            time.sleep(T_TAP)
            _adb_type(answer)
            time.sleep(T_ANIM + 0.3)
            count = _read_char_count(d)

        if count > 0:
            print(f"[glints] Text terisi: {count} char.")
            return "filled"
        else:
            print(f"[glints] Gagal isi EditText setelah 3 percobaan.")
            return "fail"
    except Exception as e:
        print(f"[glints] _handle_text_input error: {e}")
        return "fail"


def _tap_selanjutnya_enabled(d):
    """
    Tap SELANJUTNYA hanya kalau clickable=true.
    Return True kalau berhasil tap, False kalau disabled/tidak ada.
    """
    try:
        nodes = d.xpath('//*[contains(@content-desc,"SELANJUTNYA")]').all()
        for n in nodes:
            clickable = n.attrib.get("clickable", "false") == "true"
            if not clickable:
                continue
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if m:
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                d.click(cx, cy)
                return True
            n.click()
            return True
    except Exception:
        pass
    return False


def _tap_kirim_enabled(d):
    """Tap KIRIM hanya kalau clickable=true."""
    try:
        nodes = d.xpath('//*[contains(@content-desc,"KIRIM")]').all()
        for n in nodes:
            clickable = n.attrib.get("clickable", "false") == "true"
            if not clickable:
                continue
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if m:
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                d.click(cx, cy)
                return True
            n.click()
            return True
    except Exception:
        pass
    return False


def _screen_signature(d):
    """
    Ambil signature layar dari node Glints saja (exclude notification bar dll).
    Untuk deteksi stuck.
    """
    try:
        nodes = d.xpath('//*[@content-desc!=""]').all()
        descs = []
        for n in nodes:
            pkg = n.attrib.get("package", "")
            if pkg and pkg != GLINTS_PACKAGE:
                continue
            cd = n.attrib.get("content-desc", "")[:40]
            if cd:
                descs.append(cd)
        return "|".join(descs[:25])[:400]
    except Exception:
        return ""


def _dump_screen_to_file(d, path):
    """Simpan UI dump ke file untuk debugging."""
    try:
        adb_utils.adb(DEVICE_SERIAL, "shell", "uiautomator", "dump", "/sdcard/dump.xml")
        adb_utils.adb(DEVICE_SERIAL, "pull", "/sdcard/dump.xml", path)
    except Exception:
        pass


def _complete_form(d):
    """
    Navigasi form HRD Glints.
    Semua tombol pakai content-desc (React Native).

    Urutan yang mungkin muncul:
    1. Dialog 'Ada syarat yang tidak sesuai' -> LANJUTKAN atau BATALKAN
    2. Step 1..N: SELANJUTNYA (mungkin ada EditText -> isi via AI)
    3. Step terakhir: KIRIM
    """
    if not _handle_syarat_dialog(d):
        return False

    last_sig = ""
    stuck = 0

    for step in range(12):
        time.sleep(T_ANIM + 0.3)

        # 1. Dialog syarat (bisa muncul mid-form)
        if d.xpath('//*[contains(@content-desc,"Ada syarat")]').wait(timeout=0.3):
            if not _handle_syarat_dialog(d):
                return False
            continue

        # 2a. Pertanyaan proficiency bahasa
        if _handle_language_proficiency(d):
            time.sleep(T_ANIM)

        # 2b. Pertanyaan proficiency keahlian (skill)
        if _handle_skill_proficiency(d):
            time.sleep(T_ANIM)

        # 2c. Pertanyaan range pengalaman
        if _handle_experience_years(d):
            time.sleep(T_ANIM)

        # 2d. Pertanyaan Ya/Tidak
        if _handle_yes_no_question(d):
            time.sleep(T_ANIM)

        # 2c. EditText (pertanyaan text input)
        status = _handle_text_input(d)
        if status == "fail":
            print("[glints] Gagal isi text input, batalkan form.")
            return False
        if status == "filled":
            print(f"[glints]   step{step}: text terisi")
            time.sleep(T_ANIM + 0.3)

        # 3. KIRIM = final submit (hanya kalau enabled)
        if _tap_kirim_enabled(d):
            print(f"[glints]   step{step}: KIRIM ditekan -> selesai")
            time.sleep(T_LOAD + 0.3)
            return True

        # 4. SELANJUTNYA = next step (hanya kalau enabled)
        if _tap_selanjutnya_enabled(d):
            print(f"[glints]   step{step}: SELANJUTNYA ditekan")
            time.sleep(T_ANIM)
            stuck = 0
            last_sig = ""
            continue

        # Deteksi stuck: layar sama berturut-turut tanpa progress
        sig = _screen_signature(d)
        if sig and sig == last_sig:
            stuck += 1
            if stuck >= 2:
                preview = sig.replace("|", " / ")[:240]
                print(f"[glints]   step{step}: stuck. screen: {preview}")
                _dump_screen_to_file(d, r"C:\Users\Engineer02\Desktop\persona\automation\dump_stuck.xml")
                print(f"[glints]   stuck dump saved -> dump_stuck.xml")
                return False
        else:
            last_sig = sig
            stuck = 0

        time.sleep(T_ANIM)

    return False


def _back_to_results(d, keyword):
    """Tekan back dari halaman chat/detail kembali ke search results."""
    for _ in range(4):
        d.press("back")
        time.sleep(T_TAP)
        if _on_search_results(d, keyword):
            return True
    return False


def run_batch(d, limit=BATCH_SIZE):
    global _seen, _keyword_idx

    # Hanya launch fresh kalau perlu (bukan Glints atau gak di home)
    try:
        pkg = d.app_current().get("package", "")
    except Exception:
        pkg = ""
    if pkg != GLINTS_PACKAGE or not _on_home(d):
        _launch_fresh()
        _dismiss(d)
        if not _ensure_home(d):
            print("[glints] Gagal sampai ke home screen, skip batch")
            return 0

    applied = 0
    skipped = 0

    # Proses setiap keyword sampai limit terpenuhi
    attempts = 0
    while applied < limit and attempts < len(SEARCH_KEYWORDS) * 2:
        attempts += 1
        keyword = SEARCH_KEYWORDS[_keyword_idx % len(SEARCH_KEYWORDS)]

        print(f"[glints] Search: {keyword!r}")
        if not _ensure_home(d):
            _launch_fresh()
            _ensure_home(d)
        ok = _ensure_on_results(d, keyword)
        if not ok:
            print(f"[glints] Gagal navigasi ke results: {keyword}")
            _keyword_idx += 1
            continue

        found_new = False
        empty_rounds = 0

        for scroll_round in range(15):
            if applied >= limit:
                break

            cards = _get_cards(d)
            new   = [(n, desc) for n, desc in cards if hash(desc[:80]) not in _seen]

            if scroll_round == 0:
                print(f"[glints]   {len(cards)} card terdeteksi, {len(new)} baru")

            if not new:
                empty_rounds += 1
                if empty_rounds >= 3:
                    break
                d.swipe_ext("up", scale=0.8)
                time.sleep(T_TAP)
                continue
            empty_rounds = 0

            for node, desc in new:
                if applied >= limit:
                    break
                _seen.add(hash(desc[:80]))
                found_new = True

                # Skip jika sudah dilamar (badge di card)
                if _already_applied_badge(desc):
                    skipped += 1
                    continue

                position, company, salary = _parse_desc(desc)
                if not position:
                    continue

                jid = f"G|{company}|{position}"
                if state_manager.is_applied(jid):
                    print(f"[glints]   skip (state) {company} | {position}")
                    skipped += 1
                    continue
                if _blacklisted(company):
                    print(f"[glints]   skip (blacklist) {company}")
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                if not _ok_salary(salary):
                    print(f"[glints]   skip (gaji <{MIN_SALARY}) {position} | {salary}")
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                if not _fuzzy(position):
                    print(f"[glints]   skip (posisi) {position}")
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                print(f"[glints]   APPLY {company} | {position} | {salary}")

                try:
                    node.click()
                    time.sleep(T_LOAD)
                    _dismiss(d)

                    description = _extract_detail_texts(d)

                    apply_result = _tap_apply_button(d)
                    time.sleep(T_ANIM + 0.2)

                    if apply_result == "already":
                        print(f"[glints] sudah pernah dilamar: {company} | {position}")
                        state_manager.mark_applied(jid)
                        skipped += 1
                        d.press("back")
                        time.sleep(T_TAP)
                        continue

                    if apply_result == "no_button":
                        print(f"[glints] tombol apply tidak ditemukan: {position}")
                        state_manager.mark_applied(jid)
                        d.press("back")
                        time.sleep(T_TAP)
                        continue

                    ok_form = _complete_form(d)
                    smin, smax = _parse_salary_range(salary)

                    # Hanya mark applied kalau benar-benar berhasil KIRIM
                    if ok_form:
                        state_manager.mark_applied(jid)

                    if ok_form:
                        notes = " | ".join(
                            l for l in desc.split("\n")
                            if l.strip() and len(l.strip()) > 8
                        )[:200]
                        report.write_application(
                            platform="Glints",
                            company=company or "tidak diketahui",
                            position=position,
                            salary_min=smin or None,
                            salary_max=smax or None,
                            notes=notes,
                            description=description,
                        )
                        applied += 1
                        print(f"[glints] ({applied}/{limit}) {company} | {position} | {salary}")
                    else:
                        print(f"[glints] form gagal: {position}")

                    # Kembali ke search results
                    _back_to_results(d, keyword)

                except Exception as e:
                    print(f"[glints] error: {e}")
                    try:
                        for _ in range(3):
                            d.press("back")
                            time.sleep(T_TAP)
                        pkg = d.app_current().get("package", "")
                        if pkg != GLINTS_PACKAGE:
                            _launch_fresh()
                            _dismiss(d)
                            _open_search(d, keyword)
                    except Exception:
                        pass

            d.swipe_ext("up", scale=0.8)
            time.sleep(T_TAP)

        # Pindah ke keyword berikutnya
        _keyword_idx += 1

        # Jika tidak ada card baru sama sekali di keyword ini, skip
        if not found_new:
            print(f"[glints] Tidak ada card baru untuk: {keyword}")

        # Jika sudah coba semua keyword dan belum dapat limit, stop
        if _keyword_idx % len(SEARCH_KEYWORDS) == 0 and applied < limit:
            print("[glints] Semua keyword sudah dicoba")
            break

    print(f"[glints] Batch selesai: {applied} dilamar, {skipped} diskip")
    return applied
