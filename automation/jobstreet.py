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
    """Pilih resume card pertama (profile(1).pdf / Default)."""
    for kw in ["profile(1).pdf", "Default"]:
        nodes = d.xpath(f'//*[contains(@text,"{kw}")]/ancestor::*[@clickable="true"][1]').all()
        if nodes:
            nodes[0].click()
            time.sleep(T_TAP)
            return True
    # Fallback: tap center card resume pertama di area y=700-1200
    all_clickable = d.xpath('//*[@clickable="true"]').all()
    for n in all_clickable:
        b = n.attrib.get("bounds", "")
        r = _bounds_to_rect(b)
        if r:
            x1, y1, x2, y2 = r
            if 650 < y1 < 1100 and (x2 - x1) > 700:
                n.click()
                time.sleep(T_TAP)
                return True
    return False


def _select_cover_letter(d):
    """Scroll ke cover letter section dan pilih 'Write a cover letter'."""
    for _ in range(5):
        nodes = d.xpath('//*[contains(@text,"Write a cover letter")]/ancestor::*[@clickable="true"][1]').all()
        if nodes:
            nodes[0].click()
            time.sleep(T_TAP)
            return True
        d.swipe_ext("up", scale=0.45)
        time.sleep(T_TAP)
    return False


def _step1_documents(d):
    """Step 1: pilih resume + cover letter (cepat)."""
    for attempt in range(2):
        d.swipe_ext("down", scale=0.8)
        time.sleep(0.1)

        _select_resume(d)
        _select_cover_letter(d)

        _tap_text(d, "Continue", timeout=1)
        time.sleep(0.3)

        if d(textContains="required").exists(timeout=0.5):
            _tap_text(d, "OK", timeout=0.5)
            time.sleep(0.1)
            continue
        break


def _step4_submit(d):
    """Step 4: scroll cepat cari Submit, tap."""
    for _ in range(6):
        if d(text="Submit application").exists(timeout=0.3):
            break
        d.swipe_ext("up", scale=0.7)
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

    # Default: ambil opsi terakhir (biasanya yang paling skilled / lengkap)
    return options[-1] if options else None


def _answer_step2_questions(d):
    """
    Step 2 JobStreet: handle 'Select answer' dropdowns + Yes/No + EditText.
    """
    # Yes/Ya questions
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

        # Read options yang muncul
        try:
            opt_nodes = d.xpath('//*[@text!=""]').all()
            options = []
            for o in opt_nodes:
                txt = o.attrib.get("text", "").strip()
                ob = o.attrib.get("bounds", "")
                om = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", ob)
                if not om:
                    continue
                oy1 = int(om.group(2))
                # Opsi biasa kecil, exclude judul/tombol
                if oy1 < sel_y_top + 50:
                    continue
                if len(txt) > 80:
                    continue
                if txt in ("Select answer", "Continue", "Back", question):
                    continue
                options.append(txt)
            options = list(dict.fromkeys(options))[:15]  # dedupe, max 15
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

    # Step 1
    if d(textContains="Choose documents").exists(timeout=2):
        _step1_documents(d)
        time.sleep(T_ANIM + 0.5)

    # Step 2 dan 3: coba Continue, jika gagal coba jawab questions dulu
    for attempt in range(5):
        # Sudah di step 4?
        if d(textContains="Review and submit").exists(timeout=0.6) or \
           d(textContains="Submit application").exists(timeout=0.3):
            break

        # Try Continue
        if d(text="Continue").exists(timeout=1.5):
            _tap_text(d, "Continue", timeout=0.8)
            time.sleep(T_ANIM + 0.5)
            continue

        # Continue tidak ada / tidak enable -> kemungkinan ada question belum dijawab
        _answer_step2_questions(d)
        time.sleep(T_ANIM)

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

    for _ in range(40):
        if applied >= limit:
            break

        cards = _get_cards(d)
        new   = [c for c in cards if c["bounds_key"] not in _seen_jobstreet]

        if not new:
            d.swipe_ext("up", scale=0.85)
            time.sleep(T_TAP)
            continue

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
                if ok:
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

                # Kembali ke home — tap X atau back dari halaman Success
                d.press("back")
                time.sleep(T_TAP)

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

        d.swipe_ext("up", scale=0.85)
        time.sleep(T_TAP)

    print(f"[jobstreet] Batch selesai: {applied} dilamar, {skipped} diskip")
    return applied
