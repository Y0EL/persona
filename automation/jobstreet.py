import re
import time
import state_manager
import report
import adb_utils
from config import (
    DEVICE_SERIAL, JOBSTREET_PACKAGE, JOBSTREET_ACTIVITY,
    MIN_SALARY, BLACKLIST_COMPANIES, FUZZY_KEYWORDS,
    T_TAP, T_ANIM, T_LOAD, T_LAUNCH, BATCH_SIZE,
)

_seen_jobstreet: set = set()


def _launch():
    # Cepat: hanya force-stop kalau perlu (saved time)
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.1)
    adb_utils.adb(DEVICE_SERIAL, "shell", "am", "force-stop", JOBSTREET_PACKAGE)
    time.sleep(0.2)
    adb_utils.launch_app(DEVICE_SERIAL, JOBSTREET_PACKAGE, JOBSTREET_ACTIVITY, wait=T_LAUNCH)


def _tap_text(d, keyword, timeout=2, contains=False):
    try:
        el = d(textContains=keyword) if contains else d(text=keyword)
        if el.exists(timeout=timeout):
            el.click()
            return True
    except Exception:
        pass
    return False


def _dismiss(d):
    for t in ["Nanti", "Skip", "Not Now", "Close", "Tutup", "Lewati"]:
        if _tap_text(d, t, timeout=0.5):
            time.sleep(T_TAP)
            return


def login_with_google(d):
    print("[jobstreet] Login Google")
    _launch()
    _dismiss(d)
    for t in ["Sign In", "Sign in", "Login", "Masuk"]:
        if _tap_text(d, t):
            break
    time.sleep(T_LOAD)
    for t in ["Continue with Google", "Google", "Lanjutkan dengan Google"]:
        if _tap_text(d, t, contains=True):
            break
    time.sleep(T_LAUNCH + 2)
    _dismiss(d)
    state_manager.set_jobstreet_logged_in(True)
    print("[jobstreet] Login selesai")


def _bounds_to_rect(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return None


def _get_cards(d):
    """
    JobStreet: job cards = clickable+focusable View besar.
    Extract texts langsung saat detection untuk hindari masalah bounds setelah scroll.
    NB: uiautomator2 v3.5 tidak expose @class di attrib, jadi pakai @text!="" untuk filter text node.
    """
    try:
        all_tv = d.xpath('//*[@text!=""]').all()
        tv_data = []
        for t in all_tv:
            txt = t.attrib.get("text", "").strip()
            b   = t.attrib.get("bounds", "")
            r   = _bounds_to_rect(b)
            if txt and r:
                tv_data.append((txt, r))

        all_clickable = d.xpath('//*[@clickable="true" and @focusable="true"]').all()
        cards = []
        for n in all_clickable:
            b = n.attrib.get("bounds", "")
            r = _bounds_to_rect(b)
            if not r:
                continue
            x1, y1, x2, y2 = r
            # Card = lebar (>=800px), tinggi (>=300px), exclude bottom nav (y>2300)
            if (x2 - x1) < 800 or (y2 - y1) < 300 or y1 > 2300:
                continue

            # Extract texts dari TextView yang ada dalam bounds card ini
            inner = [txt for txt, tr in tv_data
                     if y1 <= tr[1] and tr[3] <= y2 and x1 <= tr[0]]
            if not inner:
                continue

            position = inner[0]
            company  = inner[1] if len(inner) > 1 else ""
            salary   = next((t for t in inner if "Rp" in t or "juta" in t.lower()), "")
            notes    = " | ".join(inner[2:6])[:200]

            cards.append({
                "node": n,
                "bounds_key": b,
                "position": position,
                "company": company,
                "salary": salary,
                "notes": notes,
                "y": y1,
            })

        return sorted(cards, key=lambda c: c["y"])
    except Exception:
        return []


def _parse_salary_range(text):
    if not text:
        return 0, 0
    clean = re.sub(r"[Rr]p\.?", "", text).replace(".", "").replace(",", "")
    clean = re.sub(r"per\s*(month|bulan)", "", clean, flags=re.IGNORECASE)
    nums  = re.findall(r"\d{6,}", clean)
    vals  = [int(n) for n in nums if 1_000_000 <= int(n) <= 300_000_000]
    return (min(vals), max(vals)) if len(vals) >= 2 else (vals[0], vals[0]) if vals else (0, 0)


def _ok_salary(text):
    if not text:
        return True
    lo, hi = _parse_salary_range(text)
    return (lo == 0 and hi == 0) or hi >= MIN_SALARY or lo >= MIN_SALARY


def _blacklisted(company):
    cl = company.lower()
    return any(b.lower() in cl for b in BLACKLIST_COMPANIES)


def _fuzzy(position):
    pl = position.lower()
    return any(k in pl for k in FUZZY_KEYWORDS)


# Lokasi yang harus di-skip (di luar Indonesia / butuh work rights khusus).
# Pakai regex word-boundary biar 'india' tidak match 'indonesia'.
_FOREIGN_PATTERN = re.compile(
    r"\b("
    r"sydney|melbourne|brisbane|perth|adelaide|canberra"
    r"|nsw|vic|qld"
    r"|wa,\s*au|act,\s*au"
    r"|australia|australian"
    r"|new\s*zealand|nz"
    r"|singapore"
    r"|kuala\s*lumpur|malaysia"
    r"|philippines|manila"
    r"|bangkok|thailand"
    r"|vietnam|hanoi|ho\s*chi\s*minh"
    r"|hong\s*kong"
    r"|india|bangalore|mumbai|delhi"
    r")\b",
    re.IGNORECASE,
)


def _foreign_location(text):
    if not text:
        return False
    return bool(_FOREIGN_PATTERN.search(text))


def _job_requires_foreign_rights(d):
    """Cek apakah halaman aplikasi blocker dengan 'right to work' di luar Indonesia."""
    try:
        for kw in ["Verify your work rights", "Right to work in", "require sponsorship"]:
            if d(textContains=kw).exists(timeout=0.5):
                return True
    except Exception:
        pass
    return False


def _extract_detail_desc(d):
    try:
        all_tv = d.xpath('//*[@class="android.widget.TextView"]').all()
        texts = [t.attrib.get("text", "").strip() for t in all_tv if len(t.attrib.get("text", "")) > 40]
        return " ".join(texts[:4])[:300]
    except Exception:
        return ""


def _select_resume(d):
    """
    Pilih resume Default (profile(1).pdf) di Step 1.
    Cari node text 'Default' (badge), tap CENTER row clickable parent via koord.
    Fallback: tap row pertama yang ada text mengandung '.pdf'.
    """
    try:
        # Cari row dengan badge "Default"
        default_nodes = d.xpath('//*[@text="Default"]').all()
        for n in default_nodes:
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            default_y = int(m.group(2))
            # Cari clickable parent row di sekitar y default badge
            all_clickable = d.xpath('//*[@clickable="true"]').all()
            for c in all_clickable:
                cb = c.attrib.get("bounds", "")
                cm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", cb)
                if not cm:
                    continue
                cy1, cy2 = int(cm.group(2)), int(cm.group(4))
                cx1, cx2 = int(cm.group(1)), int(cm.group(3))
                # Row card: y mencakup default badge, lebar > 800
                if cy1 < default_y < cy2 and (cx2 - cx1) > 800:
                    cx = (cx1 + cx2) // 2
                    cy = (cy1 + cy2) // 2
                    d.click(cx, cy)
                    time.sleep(0.3)
                    print(f"[jobstreet]   resume DEFAULT dipilih @({cx},{cy})")
                    return True

        # Fallback: cari row pertama yang ada .pdf text
        pdf_nodes = d.xpath('//*[contains(@text,".pdf")]').all()
        for n in pdf_nodes:
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            pdf_y = int(m.group(2))
            if pdf_y < 600:  # skip kalau di area header
                continue
            all_clickable = d.xpath('//*[@clickable="true"]').all()
            for c in all_clickable:
                cb = c.attrib.get("bounds", "")
                cm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", cb)
                if not cm:
                    continue
                cy1, cy2 = int(cm.group(2)), int(cm.group(4))
                cx1, cx2 = int(cm.group(1)), int(cm.group(3))
                if cy1 < pdf_y < cy2 and (cx2 - cx1) > 800:
                    cx = (cx1 + cx2) // 2
                    cy = (cy1 + cy2) // 2
                    d.click(cx, cy)
                    time.sleep(0.3)
                    print(f"[jobstreet]   resume PDF dipilih @({cx},{cy})")
                    return True
    except Exception as e:
        print(f"[jobstreet] _select_resume error: {e}")
    print(f"[jobstreet]   WARN: resume tidak terpilih!")
    return False


def _verify_resume_selected(d):
    """
    Pastikan ada radio button yang terisi di Resumé section.
    Glints uses selected="true" attribute or visual filled circle.
    """
    try:
        # Cari node selected="true" di area atas form (sebelum Continue)
        all_nodes = d.xpath('//*[@selected="true"]').all()
        if all_nodes:
            return True
        # Atau cek text "Default" yang punya parent dengan selected indicator (best effort)
        return False
    except Exception:
        return False


def _select_cover_letter(d):
    """Scroll ke cover letter section dan pilih 'Write a cover letter'."""
    for _ in range(5):
        nodes = d.xpath('//*[contains(@text,"Write a cover letter")]/ancestor::*[@clickable="true"][1]').all()
        if nodes:
            nodes[0].click()
            time.sleep(T_TAP)
            return True
        d.swipe(540, 2000, 540, 700, duration=0.04)
        time.sleep(T_TAP)
    return False


def _step1_documents(d):
    """Step 1: WAJIB pilih resume + cover letter sebelum Continue."""
    # Pastikan tab Application aktif (coord-based)
    try:
        if d(text="Job details").exists(timeout=0.4):
            d.click(171, 378)
            time.sleep(0.4)
    except Exception:
        pass

    # Scroll ke atas dulu biar resume section visible
    d.swipe(540, 400, 540, 2200, duration=0.04)
    time.sleep(0.15)

    resume_ok = False
    for attempt in range(3):
        # WAJIB pilih resume
        if _select_resume(d):
            resume_ok = True
            time.sleep(0.2)

        # Cover letter optional
        _select_cover_letter(d)
        time.sleep(0.15)

        # Scroll ke bottom cari Continue
        d.swipe(540, 2000, 540, 700, duration=0.04)
        time.sleep(0.15)

        if not resume_ok:
            # Belum dapet resume, scroll up lagi coba lagi
            d.swipe(540, 400, 540, 2200, duration=0.04)
            time.sleep(0.15)
            continue

        _tap_text(d, "Continue", timeout=1)
        time.sleep(0.4)

        if d(textContains="required").exists(timeout=0.5):
            _tap_text(d, "OK", timeout=0.5)
            time.sleep(0.1)
            # Scroll up coba pilih resume lagi
            d.swipe(540, 400, 540, 2200, duration=0.04)
            time.sleep(0.15)
            continue
        break

    if not resume_ok:
        print(f"[jobstreet]   PERINGATAN: resume mungkin tidak terpilih di Step 1!")


def _step4_submit(d):
    """Step 4: scroll cepat cari Submit, tap."""
    for _ in range(6):
        if d(text="Submit application").exists(timeout=0.3):
            break
        d.swipe(540, 2200, 540, 200, duration=0.04)
        time.sleep(0.12)

    # Tap Submit — pakai text-based dulu, fallback ke koordinat
    submitted = False
    if d(text="Submit application").exists(timeout=1):
        try:
            d(text="Submit application").click()
            submitted = True
        except Exception:
            pass

    if not submitted:
        # Fallback: cari node text "Submit application" via xpath, klik via koordinat ancestor clickable
        try:
            for n in d.xpath('//*[@text="Submit application"]').all():
                b = n.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                if m:
                    cx = (int(m.group(1)) + int(m.group(3))) // 2
                    cy = (int(m.group(2)) + int(m.group(4))) // 2
                    d.click(cx, cy)
                    submitted = True
                    break
        except Exception:
            pass

    if not submitted:
        return False

    time.sleep(T_LOAD + 1.0)

    # Sukses kalau ada salah satu indikator submit (label sukses bermacam-macam)
    success_keywords = [
        "Success", "Nice work", "has been sent", "submitted",
        "Application sent", "Aplikasi dikirim", "berhasil",
    ]
    for kw in success_keywords:
        try:
            if d(textContains=kw).exists(timeout=1.5):
                return True
        except Exception:
            pass

    # Atau cek apakah sudah keluar dari halaman aplikasi (kembali ke detail/feed)
    try:
        if not d(textContains="Review and submit").exists(timeout=0.5) and \
           not d(textContains="Submit application").exists(timeout=0.5):
            return True  # halaman ganti = submit kemungkinan sukses
    except Exception:
        pass
    return False


def _find_question_above(d, sel_y_top, sel_x_left):
    """
    Cari teks question (TextView) di atas elemen 'Select answer' tertentu.
    Question biasanya di y < sel_y_top dan x <= sel_x_left + 100.
    """
    try:
        nodes = d.xpath('//*[@text!=""]').all()
        candidates = []
        for n in nodes:
            txt = n.attrib.get("text", "").strip()
            if len(txt) < 15 or txt in (
                "Select answer", "Continue", "Back", "Job details",
                "Application", "Answer employer questions",
            ):
                continue
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            ty1, ty2 = int(m.group(2)), int(m.group(4))
            if ty2 > sel_y_top:
                continue
            candidates.append((ty1, txt))
        if not candidates:
            return ""
        # Yang paling dekat ke atas Select answer
        candidates.sort(key=lambda c: -c[0])
        return candidates[0][1]
    except Exception:
        return ""


def _pick_dropdown_option(question_text, options):
    """
    Pilih opsi terbaik dari list dropdown berdasarkan konteks pertanyaan.
    Profile Yoel: 3 thn experience, Indonesian native + English C2, willing all.
    """
    q = (question_text or "").lower()
    opt_lower = [o.lower() for o in options]

    def find(*keys):
        for k in keys:
            for i, o in enumerate(opt_lower):
                if k in o:
                    return options[i]
        return None

    # Pengalaman tahun
    if any(k in q for k in ["tahun pengalaman", "berapa tahun", "year of experience", "years of experience"]):
        return find("3 tahun", "3 years", "2-4", "1-3") or find("more than", "lebih dari") or options[-1]

    # Kemampuan bahasa Inggris
    if any(k in q for k in ["bahasa inggris", "english"]):
        return find("native", "fluent", "advanced", "lanjut", "mahir", "professional", "c2", "c1") or options[-1]

    # Ekspektasi gaji
    if any(k in q for k in ["expected salary", "ekspektasi gaji", "berapa gaji"]):
        return find("8-10", "10 juta", "rp 10", "10000000") or options[0]

    # Notice period / kapan bisa
    if any(k in q for k in ["notice", "kapan bisa", "when can", "available"]):
        return find("immediately", "segera", "1 bulan", "1 month", "2 minggu") or options[0]

    # Right to work / sponsor
    if any(k in q for k in ["right to work", "work permit", "warga negara", "wni"]):
        return find("indonesia", "wni", "yes", "ya") or options[0]

    # Education level
    if any(k in q for k in ["education", "pendidikan"]):
        return find("bachelor", "s1", "sarjana") or options[0]

    # Pemrograman / skill / framework yang dikuasai (single-select fallback)
    if any(k in q for k in ["framework", "library", "bahasa pemrograman", "language"]):
        return find("react", "python", "javascript", "typescript") or options[0]

    # Yes/No questions (2 options where one is Yes/Ya): default Yes
    yes_opt = find("ya", "yes")
    no_opt  = find("tidak", "no")
    if yes_opt and no_opt and len(options) <= 4:
        return yes_opt

    # Default: ambil opsi terakhir (biasanya yang paling skilled / lengkap)
    return options[-1] if options else None


def _fill_salary_input(d):
    """Cari salary input yang masih kosong (placeholder 'Rp' tanpa angka), isi 10000000."""
    try:
        # Cari semua TextView dengan text yang exact "Rp" atau pattern Rp tanpa angka
        nodes = d.xpath('//*[@text!=""]').all()
        for n in nodes:
            txt = n.attrib.get("text", "").strip()
            # Indikator salary kosong: hanya "Rp" atau "Rp." atau "Rp " saja
            if txt in ("Rp", "Rp.", "Rp ", "Rp 0"):
                b = n.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                if not m:
                    continue
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                d.click(cx, cy)
                time.sleep(0.3)
                # Type via uiautomator2 set_text (atau ADB fallback)
                typed = False
                try:
                    d.send_keys("10000000")
                    typed = True
                except Exception:
                    pass
                if not typed:
                    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", "10000000")
                time.sleep(0.3)
                try:
                    d.press("back")  # tutup keyboard
                except Exception:
                    pass
                time.sleep(0.15)
                print(f"[jobstreet]   salary kosong -> 10000000")
                return True
    except Exception as e:
        print(f"[jobstreet] _fill_salary_input error: {e}")
    return False


def _dismiss_validation_dialog(d):
    """Tutup dialog 'Answers required for all questions' kalau muncul."""
    try:
        if d(textContains="Answers required").exists(timeout=0.3) or \
           d(textContains="required for all").exists(timeout=0.3):
            if d(text="OK").exists(timeout=0.3):
                d(text="OK").click()
                time.sleep(0.2)
                return True
    except Exception:
        pass
    return False


def _answer_step2_questions(d):
    """
    Step 2 JobStreet: handle 'Select answer' dropdowns + Yes/No + EditText + Salary.
    Dilakukan satu per satu agar setiap question pasti terisi.
    """
    # 0. Tutup dialog validation kalau ada
    _dismiss_validation_dialog(d)

    # 1. Salary input kosong -> isi 10000000
    _fill_salary_input(d)

    # 2. Yes/Ya questions
    try:
        for label in ["Yes", "Ya"]:
            items = d.xpath(f'//*[@text="{label}"]/ancestor::*[@clickable="true"][1]').all()
            for n in items[:5]:
                try:
                    n.click()
                    time.sleep(0.12)
                except Exception:
                    pass
    except Exception:
        pass

    # 'Select answer' dropdowns
    handled_any = False
    for round_i in range(6):
        try:
            select_nodes = d.xpath('//*[@text="Select answer"]').all()
        except Exception:
            select_nodes = []
        if not select_nodes:
            break

        # Pick first unanswered Select answer
        n = select_nodes[0]
        b = n.attrib.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        if not m:
            break
        sel_y_top = int(m.group(2))
        sel_x_left = int(m.group(1))

        question = _find_question_above(d, sel_y_top, sel_x_left)

        # Tap Select answer
        try:
            cx = (int(m.group(1)) + int(m.group(3))) // 2
            cy = (int(m.group(2)) + int(m.group(4))) // 2
            d.click(cx, cy)
            time.sleep(0.3)
        except Exception:
            break

        # Read options yang muncul (di sub-page atau dropdown)
        try:
            opt_nodes = d.xpath('//*[@text!=""]').all()
            options = []
            skip_known = {
                "Select answer", "Continue", "Back", "Application",
                "Job details", "Save", "Quick apply", "OK", "Cancel",
            }
            for o in opt_nodes:
                txt = o.attrib.get("text", "").strip()
                if not txt or len(txt) > 80:
                    continue
                if txt in skip_known:
                    continue
                if question and (txt == question or txt in question):
                    continue
                # Skip step indicator
                if re.match(r"^Step\s+\d+\s+of\s+\d+$", txt):
                    continue
                # Skip baris status/error
                if "make a selection" in txt.lower():
                    continue
                # Skip question heading panjang (lebih dari 40 char dan ada tanda tanya)
                if len(txt) > 40 and "?" in txt:
                    continue
                # Skip time HH:MM atau HH.MM (status bar atau timestamp)
                if re.match(r"^\d{1,2}[:.]\d{2}$", txt):
                    continue
                # Skip greeting
                if "good morning" in txt.lower() or "good afternoon" in txt.lower() or "good evening" in txt.lower():
                    continue
                # Skip filter node package non-jobstreet (status bar)
                pkg_attr = o.attrib.get("package", "")
                if pkg_attr and pkg_attr != JOBSTREET_PACKAGE:
                    continue
                options.append(txt)
            options = list(dict.fromkeys(options))[:15]
        except Exception:
            options = []

        chosen = _pick_dropdown_option(question, options) if options else None
        if chosen:
            try:
                d(text=chosen).click()
                time.sleep(0.2)
                handled_any = True
                print(f"[jobstreet]   Q: {question[:60]} -> {chosen[:30]}")
            except Exception:
                # fallback tap koordinat option pertama yang valid
                try:
                    d.press("back")
                    time.sleep(0.2)
                except Exception:
                    pass
                break
        else:
            # Tidak ada opsi yang masuk akal, tutup dropdown
            try:
                d.press("back")
                time.sleep(0.2)
            except Exception:
                pass
            break

    # EditText kosong - tap dan ketik via AI helper
    try:
        import ai_helper as _ai
        edits = d.xpath('//*[@class="android.widget.EditText"]').all()
        for e in edits[:3]:
            try:
                cur_text = e.attrib.get("text", "").strip()
                if cur_text:
                    continue
                b = e.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
                if not m:
                    continue
                cx = (int(m.group(1)) + int(m.group(3))) // 2
                cy = (int(m.group(2)) + int(m.group(4))) // 2
                d.click(cx, cy)
                time.sleep(0.2)
                ans = _ai._static_answer("describe your experience")
                safe = ans.replace(" ", "%s")[:200]
                adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", safe)
                time.sleep(0.2)
                d.press("back")
                time.sleep(0.15)
            except Exception:
                pass
    except Exception:
        pass

    return handled_any


def _close_to_feed(d):
    """Tutup halaman Success/detail. Klik X kiri atas, fallback back press."""
    try:
        # X biasanya di kiri atas (12,138 atau sekitar)
        for _ in range(3):
            # Cek apakah masih di halaman application/success
            if d(textContains="Success").exists(timeout=0.3) or \
               d(textContains="Nice work").exists(timeout=0.3) or \
               d(textContains="Step ").exists(timeout=0.3) or \
               d(textContains="Application").exists(timeout=0.3):
                # Tap X close
                d.click(80, 200)
                time.sleep(0.3)
                # Konfirmasi "Discard application?" -> Discard
                if d(text="Discard").exists(timeout=0.5):
                    d(text="Discard").click()
                    time.sleep(0.3)
                continue
            # Sudah keluar
            return True
        d.press("back")
        time.sleep(0.15)
    except Exception:
        pass
    return False


def _scroll_for_more_cards(d):
    """Scroll dalam beberapa kali biar dapat lebih banyak card di JS feed."""
    for _ in range(4):
        d.swipe(540, 2200, 540, 200, duration=0.04)
        time.sleep(0.15)


def _tap_refresh(d):
    """Tap tombol Refresh kalau ada untuk pull cards baru."""
    try:
        if d(text="Refresh").exists(timeout=0.5):
            d(text="Refresh").click()
            time.sleep(1.0)
            return True
    except Exception:
        pass
    return False


def _switch_tab(d, label):
    """
    Switch ke tab di JobStreet feed: 'All' / 'New to you' / 'Recommended'.
    Return True kalau berhasil tap.
    """
    if not _ensure_jobstreet(d):
        time.sleep(1.5)
    try:
        # Cari node text=label DI DALAM JobStreet package (filter)
        nodes = d.xpath(f'//*[@text="{label}"]').all()
        for n in nodes:
            pkg = n.attrib.get("package", "")
            if pkg and pkg != JOBSTREET_PACKAGE:
                continue
            b = n.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            cy = (int(m.group(2)) + int(m.group(4))) // 2
            # Tab harus di area atas (y < 800)
            if cy > 800:
                continue
            cx = (int(m.group(1)) + int(m.group(3))) // 2
            d.click(cx, cy)
            time.sleep(0.5)
            return True
    except Exception:
        pass
    return False


def _scroll_to_feed_top(d):
    """Scroll ke atas penuh untuk lihat tab Recommended/All/New to you."""
    for _ in range(5):
        d.swipe(540, 400, 540, 2200, duration=0.04)
        time.sleep(0.08)


# Keyword search JobStreet sesuai profile Yoel (expanded)
JS_SEARCH_KEYWORDS = [
    "AI Engineer", "Machine Learning Engineer",
    "Agentic AI", "LLM Engineer", "Prompt Engineer",
    "Forward Deployed Engineer",
    "Backend Developer", "Python Developer",
    "Node JS Developer", "Java Developer",
    "Full Stack Developer", "Fullstack Engineer",
    "Frontend Developer", "React Developer",
    "Vue Developer", "Next JS Developer",
    "Software Engineer", "Software Developer",
    "Web Developer",
    "DevOps Engineer", "Cloud Engineer",
    "Platform Engineer", "SRE",
    "Data Engineer", "Data Scientist", "Data Analyst",
    "IT Support", "IT Specialist", "IT Engineer",
    "Mobile Developer", "Flutter Developer",
    "Blockchain Developer", "Smart Contract Developer",
    "Tech Lead", "Senior Engineer",
]


def _search_js(d, keyword):
    """
    Buka search bar JobStreet, ketik keyword, submit ke results page.

    Real flow JS (verified live 2026-05-17):
      1. Tap top search bar "Continue your job search" -> opens MODAL
         dengan 2 fields (Describe / Enter suburb) + filters + tombol SEEK.
      2. Tap "Describe what you're looking for" field -> opens secondary
         SUGGESTION INPUT page dengan keyboard.
      3. Type keyword.
      4. Press ENTER -> returns ke modal, field terisi, tombol jadi "SEEK N Jobs".
      5. Tap SEEK button -> results page.
      6. Dismiss "Save this search" banner kalau muncul.
    """
    if not _ensure_jobstreet(d):
        time.sleep(1.5)
    _go_to_home_tab(d)

    try:
        # 1. Tap top search bar (y=354 = "Continue your job search")
        d.click(540, 354)
        time.sleep(1.0)

        # 2. Tap "Describe what you're looking for" field (modal first input)
        #    Bounds: [48,354][1032,507], center y=430
        d.click(540, 430)
        time.sleep(1.0)

        # 3. Clear existing text + type keyword di suggestion page
        try:
            adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
            adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_DEL")
        except Exception:
            pass
        time.sleep(0.2)
        safe = keyword.replace(" ", "%s")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", safe)
        time.sleep(0.4)

        # 4. Press ENTER -> back to modal dengan field terisi
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_ENTER")
        time.sleep(1.5)

        # 5. Tap SEEK button. Text dinamis: "SEEK N Jobs" / "SEEK".
        clicked = False
        for sel_kwargs in (
            {"textStartsWith": "SEEK "},
            {"text": "SEEK"},
        ):
            try:
                el = d(**sel_kwargs)
                if el.exists(timeout=1.5):
                    el.click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            # Fallback koordinat: pink SEEK button area [48,1488][1032,1632]
            d.click(540, 1560)
        time.sleep(2.5)

        # 6. Dismiss "Save this search" banner di kanan bawah results
        #    (cuma muncul untuk keyword baru). Klik X-nya kalau ada,
        #    atau just leave it — gak interfere card tap.
        try:
            for label in ["Not now", "Dismiss", "Maybe later"]:
                btn = d(text=label)
                if btn.exists(timeout=0.4):
                    btn.click()
                    time.sleep(0.3)
                    break
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[jobstreet] search error: {e}")
    return False


def _ensure_jobstreet(d):
    """Pastikan device di app JobStreet. Relaunch kalau tidak."""
    try:
        pkg = d.app_current().get("package", "")
    except Exception:
        pkg = ""
    if pkg != JOBSTREET_PACKAGE:
        _launch()
        time.sleep(0.5)
        return False  # relaunched
    return True


def _go_to_home_tab(d):
    """Klik Home tab di bottom nav (koordinat tetap, bukan teks)."""
    _ensure_jobstreet(d)
    # Bottom nav Home di koordinat tetap berdasarkan UI dump
    # Home center sekitar (144, 2316) berdasarkan bounds [98,2296][190,2336]
    try:
        d.click(144, 2316)
        time.sleep(0.5)
        return True
    except Exception:
        pass
    return False


def _complete_apply(d):
    """
    Selesaikan 4 step Quick Apply JobStreet.
    Step 1: Choose documents (resume + cover letter)
    Step 2: Answer employer questions
    Step 3: Update Jobstreet Profile (auto)
    Step 4: Review and submit
    """
    # Pre-check: lowongan luar negeri yang minta verify work rights
    if _job_requires_foreign_rights(d):
        print("[jobstreet] skip (work rights asing)")
        try:
            d.press("back")
            time.sleep(T_TAP)
        except Exception:
            pass
        return False

    # Pastikan tab Application aktif (bukan Job details) - tap coord (kiri atas tab)
    try:
        if d(text="Job details").exists(timeout=0.4):
            # Application tab di bounds [48,350][295,406], center (171, 378)
            d.click(171, 378)
            time.sleep(0.4)
    except Exception:
        pass

    # Step 1
    if d(textContains="Choose documents").exists(timeout=2):
        _step1_documents(d)
        time.sleep(T_ANIM + 0.5)

    # Step 2 dan 3: jawab semua question dulu (scroll bertahap), lalu Continue
    for attempt in range(8):
        # Sudah di step 4?
        if d(textContains="Review and submit").exists(timeout=0.4) or \
           d(textContains="Submit application").exists(timeout=0.3):
            break

        # Tutup dialog 'Answers required' kalau ada
        if _dismiss_validation_dialog(d):
            # Setelah dismiss, scroll up cari question kosong dan isi
            d.swipe(540, 400, 540, 2200, duration=0.04)  # scroll ke atas
            time.sleep(0.2)
            _answer_step2_questions(d)
            # Scroll bertahap ke bawah sambil isi
            for _ in range(4):
                d.swipe(540, 2200, 540, 600, duration=0.04)
                time.sleep(0.15)
                _answer_step2_questions(d)
            time.sleep(0.2)
            continue

        # Coba isi questions (kalau ada Select answer / salary kosong)
        _answer_step2_questions(d)

        # Tap Continue
        if d(text="Continue").exists(timeout=0.8):
            _tap_text(d, "Continue", timeout=0.5)
            time.sleep(0.4)
            continue

        # Tidak ada Continue dan tidak ada dialog, scroll cari
        d.swipe(540, 2200, 540, 600, duration=0.04)
        time.sleep(0.15)

    # Step 4: Submit
    if d(textContains="Review and submit").exists(timeout=2) or \
       d(textContains="Submit application").exists(timeout=1):
        return _step4_submit(d)

    return False


def run_batch(d, limit=BATCH_SIZE):
    global _seen_jobstreet

    try:
        current = d.app_current().get("package", "")
    except Exception:
        current = ""
    if current != JOBSTREET_PACKAGE:
        _launch()
        _dismiss(d)

    applied = 0
    skipped = 0

    # Sumber card: pertama tabs, lalu search keyword
    sources = [("tab", t) for t in ["All", "New to you", "Recommended"]]
    sources += [("search", kw) for kw in JS_SEARCH_KEYWORDS]

    for src_type, src_label in sources:
        if applied >= limit:
            break

        if src_type == "tab":
            _go_to_home_tab(d)
            _scroll_to_feed_top(d)
            switched = _switch_tab(d, src_label)
            if switched:
                print(f"[jobstreet] tab -> {src_label}")
        else:
            _go_to_home_tab(d)
            _scroll_to_feed_top(d)
            if _search_js(d, src_label):
                print(f"[jobstreet] search -> {src_label}")
            else:
                continue
        empty_streak = 0

        for iter_n in range(50):
            if applied >= limit:
                break

            cards = _get_cards(d)
            new   = [c for c in cards if c["bounds_key"] not in _seen_jobstreet]

            if iter_n == 0 or new:
                print(f"[jobstreet]   {len(cards)} card terdeteksi, {len(new)} baru")

            if not new:
                empty_streak += 1
                if empty_streak % 5 == 0:
                    _tap_refresh(d)
                d.swipe(540, 2200, 540, 200, duration=0.04)
                time.sleep(0.1)
                if empty_streak >= 12:
                    # Pindah ke tab berikutnya
                    break
                continue
            empty_streak = 0

            for card in new:
                if applied >= limit:
                    break
                _seen_jobstreet.add(card["bounds_key"])

                position = card["position"]
                company  = card["company"]
                salary   = card["salary"]
                notes    = card["notes"]

                if not position:
                    continue

                jid = f"JS|{company}|{position}"
                if state_manager.is_applied(jid):
                    skipped += 1
                    continue
                if _blacklisted(company):
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                if not _ok_salary(salary):
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                if not _fuzzy(position):
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue
                if _foreign_location(notes) or _foreign_location(company) or _foreign_location(position):
                    print(f"[jobstreet] skip (lokasi asing) {position} | {notes[:80]}")
                    state_manager.mark_applied(jid)
                    skipped += 1
                    continue

                print(f"[jobstreet]   APPLY {company} | {position} | {salary}")
                try:
                    card["node"].click()
                    time.sleep(T_LOAD)
                    _dismiss(d)

                    # Ambil deskripsi dari halaman detail
                    description = _extract_detail_desc(d)

                    if not _tap_text(d, "Quick apply", timeout=2):
                        d.press("back")
                        continue
                    time.sleep(T_ANIM + 0.3)

                    ok = _complete_apply(d)
                    smin, smax = _parse_salary_range(salary)

                    # Hanya mark applied kalau benar-benar berhasil submit
                    if ok:
                        state_manager.mark_applied(jid)
                        report.write_application(
                            platform="JobStreet",
                            company=company or "tidak diketahui",
                            position=position,
                            salary_min=smin or None,
                            salary_max=smax or None,
                            notes=notes,
                            description=description,
                        )
                        applied += 1
                        print(f"[jobstreet] ({applied}/{limit}) {company} | {position} | {salary}")
                    else:
                        print(f"[jobstreet] form tidak selesai: {position}")

                    # Tutup halaman Success / form: tap X (kiri atas) lalu back ke feed
                    _close_to_feed(d)

                except Exception as e:
                    print(f"[jobstreet] error: {e}")
                    try:
                        d.press("back")
                        if d.app_current().get("package", "") != JOBSTREET_PACKAGE:
                            _launch()
                            _dismiss(d)
                    except Exception:
                        pass
                    time.sleep(T_TAP)

            # Scroll untuk load card berikutnya di feed yang sama
            d.swipe(540, 2200, 540, 200, duration=0.04)
            time.sleep(T_TAP)

    print(f"[jobstreet] Batch selesai: {applied} dilamar, {skipped} diskip")
    return applied
