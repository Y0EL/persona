"""
Indeed Easy Apply automation module.

Flow:
  1. Launch app -> tap Beranda tab.
  2. Iterate "Jobs for you" feed dengan badge "Easily apply".
  3. Tap card -> detail page -> tap "Lamar sekarang".
  4. Form multi-step (resume page, questions page, dst):
     - Resume: pre-selected, scroll + Continue.
     - Questions: Yes/No radios via heuristic, text input via AI.
  5. Submit -> mark applied + AI summary ke report.
"""
import re
import time

import adb_utils
import state_manager
import report
import ai_helper
from config import (
    DEVICE_SERIAL, BATCH_SIZE,
    BLACKLIST_COMPANIES, FUZZY_KEYWORDS,
    T_TAP, T_ANIM, T_LOAD, T_LAUNCH,
)

INDEED_PACKAGE  = "com.indeed.android.jobsearch"
INDEED_ACTIVITY = "com.indeed.android.jobsearch/.LaunchActivity"

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

_seen: set = set()

SKIP_COUNTERS: dict = {}
SAMPLE_SKIPPED: list = []


def _track_skip(company, position, reason):
    SKIP_COUNTERS[reason] = SKIP_COUNTERS.get(reason, 0) + 1
    if len(SAMPLE_SKIPPED) < 30:
        SAMPLE_SKIPPED.append((company or "?", position or "?", reason))


def get_session_stats():
    return dict(SKIP_COUNTERS), list(SAMPLE_SKIPPED)


def reset_session_stats():
    SKIP_COUNTERS.clear()
    SAMPLE_SKIPPED.clear()


# ====================== APP LIFECYCLE ======================

def _launch_fresh():
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.3)
    adb_utils.adb(DEVICE_SERIAL, "shell", "am", "force-stop", INDEED_PACKAGE)
    time.sleep(0.6)
    adb_utils.launch_app(DEVICE_SERIAL, INDEED_PACKAGE, INDEED_ACTIVITY, wait=int(T_LAUNCH) + 3)


def _on_beranda(d):
    try:
        if d.xpath('//*[@content-desc="Beranda" or @text="Beranda"]').wait(timeout=0.5):
            for kw in ["Jobs for you", "Welcome,", "Lowongan untukmu"]:
                if d.xpath(f'//*[contains(@text,"{kw}")]').wait(timeout=0.3):
                    return True
    except Exception:
        pass
    return False


def _goto_beranda(d, max_attempts=3):
    for _ in range(max_attempts):
        if _on_beranda(d):
            return True
        # Tap Beranda di bottom nav (coordinates dari probe: [36,2258][288,2388])
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "tap", "162", "2323")
        time.sleep(T_LOAD)
    return _on_beranda(d)


# ====================== CARD EXTRACTION ======================

def _bounds(s):
    m = _BOUNDS_RE.match(s or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def _get_easy_apply_cards(d):
    """
    Cari card dengan 'Easily apply' badge di Beranda.
    Return list of dict {tap_y}.
    """
    cards = []
    try:
        nodes = d.xpath('//*[@text="Easily apply" or contains(@content-desc,"Easily apply")]').all()
        seen_y = set()
        for n in nodes:
            b = _bounds(n.attrib.get("bounds", ""))
            if not b:
                continue
            x1, y1, x2, y2 = b
            # badge sendiri kecil (lebar < 400). Tap area = badge_y + offset
            if (x2 - x1) > 400:
                continue
            # Skip badge yang offscreen / di bottom nav (y > 2200)
            if y1 < 400 or y1 > 2200:
                continue
            # Card center: tap di tengah card. Heuristic: card height 300-400,
            # badge biasanya di TOP card -> tap_y = badge_y + 180
            tap_y = min(y1 + 180, 2100)
            # Dedup by bucket of 100px
            bucket = tap_y // 100
            if bucket in seen_y:
                continue
            seen_y.add(bucket)
            cards.append({"tap_y": tap_y, "badge_y": y1})
    except Exception as e:
        print(f"[indeed] _get_easy_apply_cards error: {e}")
    return cards


def _read_detail_company_title(d):
    """
    Setelah tap card, baca title (besar) + company (kecil) dari detail page.
    """
    try:
        nodes = d.xpath('//*[@text!=""]').all()
        infos = []
        for n in nodes:
            t = n.attrib.get("text", "").strip()
            if not t or len(t) < 3:
                continue
            b = _bounds(n.attrib.get("bounds", ""))
            if not b:
                continue
            x1, y1, x2, y2 = b
            if y1 > 800:
                continue  # only top portion
            infos.append((y1, t))
        infos.sort()
        title = ""
        company = ""
        for y, t in infos:
            tl = t.lower()
            if tl in ("keluar", "back", "bagikan", "simpan", "share", "save"):
                continue
            if not title and len(t) > 8:
                title = t
                continue
            if title and not company and 2 < len(t) < 60 and "•" not in t and "·" not in t:
                # company biasanya di bawah title, single line
                company = t.split(",")[0].strip()
                break
        return company, title
    except Exception:
        return "", ""


def _extract_full_job_context(d):
    """Grab raw text dari job detail page untuk AI summary."""
    try:
        chunks = []
        seen = set()
        for n in d.xpath('//*[@text!=""]').all():
            t = n.attrib.get("text", "").strip()
            if not t or len(t) < 8 or t in seen:
                continue
            low = t.lower()
            if any(s in low for s in ["keluar", "kembali", "bagikan", "lamar sekarang", "report job"]):
                continue
            seen.add(t)
            chunks.append(t[:400])
            if len(chunks) >= 40:
                break
        return "\n".join(chunks)
    except Exception:
        return ""


# ====================== FILTERS ======================

def _blacklisted(company):
    if not company:
        return False
    lo = company.lower()
    return any(b.lower() in lo for b in BLACKLIST_COMPANIES)


def _fuzzy(title):
    if not title:
        return True
    lo = title.lower()
    return any(kw in lo for kw in FUZZY_KEYWORDS)


def _job_id(company, title):
    return f"indeed:{(company or '').strip().lower()}:{(title or '').strip().lower()}"


# ====================== APPLY FLOW ======================

def _tap_lamar(d):
    """Tap 'Lamar sekarang' button di job detail page."""
    try:
        node = d.xpath('//*[@text="Lamar sekarang" or @text="Apply now"]')
        if node.wait(timeout=2.5):
            node.click()
            return True
    except Exception:
        pass
    return False


def _on_apply_form(d):
    """Check kalau lagi di Indeed apply form (header 'Keluar' top-right)."""
    try:
        if d.xpath('//*[@text="Keluar"]').wait(timeout=0.6):
            return True
        if d.xpath('//*[@text="Continue" or @text="Lanjutkan"]').wait(timeout=0.5):
            return True
    except Exception:
        pass
    return False


def _close_apply_form(d):
    """Tap Keluar + confirm discard (Indeed: Tutup tanpa simpan)."""
    try:
        node = d.xpath('//*[@text="Keluar"]')
        if node.wait(timeout=1):
            node.click()
            time.sleep(T_ANIM)
            # confirm dialog (Indonesian)
            for label in ["Buang", "Discard", "Tutup tanpa simpan", "Yes", "Ya"]:
                btn = d.xpath(f'//*[@text="{label}"]')
                if btn.wait(timeout=0.5):
                    btn.click()
                    time.sleep(T_ANIM)
                    break
    except Exception:
        pass


def _answer_radio_yes_no(d, question_text):
    """
    Untuk Yes/No radio: pilih jawaban based on AI Yes/No.
    Cari radio yang text-nya "Yes"/"No"/"Ya"/"Tidak" terdekat dengan question_text.
    """
    ans = ai_helper.answer_question(question_text, max_chars=100)
    is_yes = any(ans.lower().startswith(p) for p in ["yes", "ya"])
    target = "Yes" if "yes" in (ans.lower()[:10] + "english") else "Ya"
    # Default to Yes
    for label in (["Yes", "Ya"] if is_yes else ["No", "Tidak"]):
        try:
            node = d.xpath(f'//*[@text="{label}"]')
            if node.wait(timeout=0.4):
                node.click()
                time.sleep(T_TAP)
                return True
        except Exception:
            pass
    return False


def _find_unfilled_questions(d):
    """
    Indeed form: questions berupa text dengan tanda `*` (required).
    Returns list of (question_text, edit_node_or_radio_y).
    """
    results = []
    try:
        text_nodes = d.xpath('//*[@text!=""]').all()
        edits = d.xpath('//*[@class="android.widget.EditText"]').all()

        # Map question text + nearest below edit/radio
        for tn in text_nodes:
            qt = tn.attrib.get("text", "").strip()
            if not qt or len(qt) < 8:
                continue
            if not (qt.endswith("?") or "*" in qt or qt.lower().startswith(("do ", "are ", "have ", "can ", "apakah", "berapa", "how many"))):
                continue
            b = _bounds(tn.attrib.get("bounds", ""))
            if not b:
                continue
            qy = b[3]  # bottom of question
            # Find nearest EditText below
            for e in edits:
                eb = _bounds(e.attrib.get("bounds", ""))
                if not eb:
                    continue
                etxt = e.attrib.get("text", "").strip()
                if etxt:
                    continue
                if 0 < (eb[1] - qy) < 250:
                    results.append((qt, e, "text"))
                    break
            else:
                # Maybe radio question (no EditText below) -> just record
                results.append((qt, None, "radio"))
        return results
    except Exception:
        return []


def _fill_text_question(d, node, question):
    try:
        node.click()
        time.sleep(T_TAP)
        is_numeric = any(k in question.lower() for k in ["how many", "berapa", "tahun", "years"])
        ans = ai_helper.answer_question(question, max_chars=200) or "3"
        if is_numeric and not re.search(r"\d", ans):
            ans = "3"
        if is_numeric:
            ans = re.findall(r"\d+", ans)[0] if re.findall(r"\d+", ans) else "3"
        safe = ans.replace(" ", "%s").replace("'", "").replace('"', "")[:200]
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", safe)
        time.sleep(T_TAP)
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_TAP)
        print(f"[indeed]   fill '{question[:40]}' -> '{ans[:30]}'")
        return True
    except Exception as e:
        print(f"[indeed]   fill gagal: {e}")
        return False


def _tap_continue(d):
    """Scroll bottom, tap Continue/Lanjutkan."""
    try:
        # scroll to bottom (Indeed form bisa panjang)
        for _ in range(2):
            adb_utils.adb(DEVICE_SERIAL, "shell", "input", "swipe", "540", "1800", "540", "600", "300")
            time.sleep(T_TAP)
        for label in ["Continue", "Lanjutkan", "Submit your application", "Submit", "Kirim aplikasi"]:
            node = d.xpath(f'//*[@text="{label}"]')
            if node.wait(timeout=0.6):
                # Get bounds for coordinate click (Indeed buttons can have [0,0][0,0])
                b = _bounds(node.attrib.get("bounds", "") if hasattr(node, "attrib") else "")
                # Use xpath click which falls back to center
                node.click()
                time.sleep(T_LOAD + 1)
                return label
    except Exception:
        pass
    return None


def _submit_flow(d, max_steps=8):
    """
    Loop Continue → fill question → Continue → ... → Submit.
    Return True kalau berhasil submit.
    """
    last_screen_sig = None
    stuck = 0
    for step in range(max_steps):
        time.sleep(T_LOAD)

        # Check sukses (post-apply page)
        for ok_kw in ["You've applied", "Aplikasi Anda dikirim", "Application sent",
                      "Aplikasi terkirim", "Lamaran Anda telah dikirim"]:
            try:
                if d.xpath(f'//*[contains(@text,"{ok_kw}")]').wait(timeout=0.3):
                    print(f"[indeed]   submitted ('{ok_kw}')")
                    return True
            except Exception:
                pass

        # Fill unfilled questions
        qs = _find_unfilled_questions(d)
        for qt, node, qtype in qs[:3]:
            if qtype == "text" and node is not None:
                _fill_text_question(d, node, qt)
            elif qtype == "radio":
                _answer_radio_yes_no(d, qt)

        # Tap Continue/Submit
        btn = _tap_continue(d)
        if not btn:
            print(f"[indeed]   no advance button di step {step}")
            return False

        # Stuck detection (same screen 2x)
        try:
            sig = d.dump_hierarchy()[:2000]
            if sig == last_screen_sig:
                stuck += 1
                if stuck >= 2:
                    print(f"[indeed]   stuck setelah {btn}, abort")
                    return False
            else:
                stuck = 0
            last_screen_sig = sig
        except Exception:
            pass

    return False


def _apply_to_card(d, tap_y):
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "tap", "540", str(tap_y))
    time.sleep(T_LOAD + 1)

    company, title = _read_detail_company_title(d)
    if not title:
        print(f"[indeed]   no title, skip")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, "", "", ""

    jid = _job_id(company, title)
    if jid in _seen:
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""
    _seen.add(jid)

    if state_manager.is_applied(jid):
        print(f"[indeed]   skip (state) {company} | {title}")
        _track_skip(company, title, "state")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""
    if _blacklisted(company):
        print(f"[indeed]   skip (blacklist) {company}")
        _track_skip(company, title, "blacklist")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""
    if not _fuzzy(title):
        print(f"[indeed]   skip (fuzzy) {title}")
        _track_skip(company, title, "fuzzy-mismatch")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""

    print(f"[indeed]   APPLY {company} | {title}")
    raw_context = _extract_full_job_context(d)

    if not _tap_lamar(d):
        print(f"[indeed]   no Lamar button, skip")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""

    time.sleep(T_LOAD + 2)
    if not _on_apply_form(d):
        print(f"[indeed]   form tidak terbuka")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""

    ok = _submit_flow(d)
    if not ok:
        _close_apply_form(d)
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title, ""

    _goto_beranda(d)
    return True, company, title, raw_context


# ====================== MAIN ENTRY ======================

def run_batch(d, limit=BATCH_SIZE):
    global _seen

    _launch_fresh()
    time.sleep(T_LAUNCH + 1)

    if not _goto_beranda(d):
        print("[indeed] gagal navigasi ke Beranda")
        return 0

    applied = 0
    scroll_count = 0
    max_scrolls = 6
    tried = set()

    while applied < limit and scroll_count < max_scrolls:
        cards = _get_easy_apply_cards(d)
        new_cards = [c for c in cards if c["tap_y"] not in tried]
        if not new_cards:
            adb_utils.adb(DEVICE_SERIAL, "shell", "input", "swipe", "540", "1800", "540", "600", "300")
            time.sleep(T_LOAD)
            scroll_count += 1
            continue

        for card in new_cards:
            if applied >= limit:
                break
            tried.add(card["tap_y"])
            ok, company, title, raw = _apply_to_card(d, card["tap_y"])
            if ok:
                jid = _job_id(company, title)
                state_manager.mark_applied(jid)
                ai_summary = ""
                try:
                    ai_summary = ai_helper.summarize_job(raw, company, title)
                except Exception as e:
                    print(f"[indeed] AI summary gagal: {e}")
                report.write_application(
                    platform="Indeed",
                    company=company,
                    position=title,
                    salary_min=0, salary_max=0,
                    notes="Easily Apply via Indeed feed",
                    description="",
                    ai_summary=ai_summary,
                )
                applied += 1
                print(f"[indeed] ({applied}/{limit}) {company} | {title}")
                time.sleep(T_LOAD)

    print(f"[indeed] batch done: {applied} apply, scroll {scroll_count}x")
    return applied
