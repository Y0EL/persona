"""
LinkedIn Easy Apply automation module.

Strategi:
  1. Launch app -> tap Jobs tab (bottom nav).
  2. Scroll list "Top job picks for you" + manual search keyword.
  3. Untuk tiap card berlabel "Easy Apply":
     - Cek fuzzy keyword match, blacklist, sudah-applied.
     - Tap card -> tap tombol "Easy Apply" di detail.
     - Loop Next -> Review -> Submit. Form sebagian besar pre-filled dari profile.
     - Page yang punya pertanyaan tambahan: deteksi EditText kosong, isi via
       ai_helper.answer_question. Kalau gagal advance setelah Next 2x, batalkan
       lamaran job ini (close X) dan lanjut card berikutnya.
  4. Mark applied di state.json + report ke Lamaran/<dd><mm><yyyy>.md.
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

LINKEDIN_PACKAGE  = "com.linkedin.android"
LINKEDIN_ACTIVITY = "com.linkedin.android/.authenticator.LaunchActivityDefault"

SEARCH_KEYWORDS = [
    # Core AI / ML
    "AI Engineer Jakarta", "Machine Learning Engineer Indonesia",
    "LLM Engineer", "Agentic AI", "Forward Deployed Engineer",
    # Software
    "Software Engineer Jakarta", "Full Stack Developer Jakarta",
    "Backend Developer Indonesia", "Python Developer Jakarta",
    # Data Engineer only — pipeline/backend. Skip Data Scientist/Analyst/BI (off-fit).
    "Data Engineer Jakarta",
    # Frontend
    "Frontend Developer Jakarta", "React Developer Indonesia",
    # Blockchain
    "Blockchain Developer", "Solidity Developer",
]

_seen: set = set()

# Skip reason tracking (per session) untuk retrospective AI.
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

def _launch_fresh(d):
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.3)
    adb_utils.adb(DEVICE_SERIAL, "shell", "am", "force-stop", LINKEDIN_PACKAGE)
    time.sleep(0.6)
    adb_utils.launch_app(DEVICE_SERIAL, LINKEDIN_PACKAGE, LINKEDIN_ACTIVITY, wait=int(T_LAUNCH) + 2)


def _on_jobs_tab(d):
    """Cek apakah kita di Jobs tab via content-desc 'Jobs 5 of 5'."""
    try:
        if d.xpath('//*[contains(@content-desc,"Jobs 5 of 5")]').wait(timeout=0.5):
            # Pastikan juga ada teks 'Top job picks' atau search bar 'Describe'
            for kw in ["Top job picks", "Describe the job", "Recommended for you"]:
                if d.xpath(f'//*[contains(@text,"{kw}")]').wait(timeout=0.3):
                    return True
    except Exception:
        pass
    return False


def _goto_jobs_tab(d, max_attempts=4):
    """Pastikan kita di Jobs tab. Tap bottom nav 'Jobs 5 of 5'."""
    for _ in range(max_attempts):
        if _on_jobs_tab(d):
            return True
        # Coba tap via xpath
        try:
            node = d.xpath('//*[contains(@content-desc,"Jobs 5 of 5")]')
            if node.wait(timeout=1):
                node.click()
                time.sleep(T_LOAD)
                continue
        except Exception:
            pass
        # Fallback: tap koordinat known
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "tap", "972", "2316")
        time.sleep(T_LOAD)
    return _on_jobs_tab(d)


# ====================== CARD ENUM ======================

def _scroll_jobs(d):
    """Scroll down di Jobs tab untuk load lebih banyak card."""
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "swipe", "540", "1800", "540", "600", "300")
    time.sleep(T_LOAD)


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_NODE_RE = re.compile(
    r'<node[^>]*?text="([^"]*)"[^>]*?content-desc="([^"]*)"[^>]*?clickable="(true|false)"[^>]*?bounds="(\[\d+,\d+\]\[\d+,\d+\])"',
    re.DOTALL,
)
_LOCATION_HINT = re.compile(
    r"\b(jakarta|indonesia|metropolitan|hybrid|remote|on-site|tangerang|bekasi|bandung)\b",
    re.IGNORECASE,
)


def _parse_nodes(xml):
    """Parse XML hierarchy ke list dict: {text, desc, clickable, x1,y1,x2,y2}."""
    nodes = []
    for m in _NODE_RE.finditer(xml):
        bm = _BOUNDS_RE.match(m.group(4))
        if not bm:
            continue
        nodes.append({
            "text": m.group(1),
            "desc": m.group(2),
            "clickable": m.group(3) == "true",
            "x1": int(bm.group(1)), "y1": int(bm.group(2)),
            "x2": int(bm.group(3)), "y2": int(bm.group(4)),
        })
    return nodes


def _get_visible_cards(d):
    """
    Cari full-width clickable card di Jobs tab yang punya Easy Apply badge di dalamnya.
    Return list of {tap_y, y1, y2}.
    """
    cards = []
    try:
        xml = d.dump_hierarchy()
        nodes = _parse_nodes(xml)

        # Full-width clickable cards (x1==0, x2==1080, height 100-500)
        cards_raw = [
            n for n in nodes
            if n["clickable"]
            and n["x1"] == 0 and n["x2"] == 1080
            and n["y1"] >= 600
            and 100 <= (n["y2"] - n["y1"]) <= 600
        ]

        # Easy Apply badges
        ea_badges = [
            n for n in nodes
            if ("Easy Apply" in n["desc"] or "Easy Apply" in n["text"])
            and (n["x2"] - n["x1"]) < 400  # badge size
        ]

        seen_y = set()
        for card in cards_raw:
            # Check apakah badge ada di dalam bounds card
            has_ea = any(
                card["y1"] <= b["y1"] <= card["y2"]
                for b in ea_badges
            )
            if not has_ea:
                continue
            ty = (card["y1"] + card["y2"]) // 2
            if ty in seen_y:
                continue
            seen_y.add(ty)
            cards.append({"tap_y": ty, "y1": card["y1"], "y2": card["y2"]})
    except Exception as e:
        print(f"[linkedin] _get_visible_cards error: {e}")
    return cards


def _read_detail_title_company(d):
    """
    Setelah tap card, baca company + title dari job detail page.
    Detail page: company di atas (small), title besar di bawahnya.
    """
    try:
        xml = d.dump_hierarchy()
        nodes = _parse_nodes(xml)
        text_nodes = [n for n in nodes if n["text"] and len(n["text"]) > 2]
        text_nodes.sort(key=lambda n: n["y1"])

        company = ""
        title = ""
        for n in text_nodes:
            t = n["text"].strip()
            if not t or len(t) < 2:
                continue
            # Skip toolbar / search bar / common UI texts
            if t.lower() in ("describe the job you want", "save", "easy apply", "more"):
                continue
            if _LOCATION_HINT.search(t):
                continue
            # First non-UI text in 200-1200 y range tends to be company name
            if 200 <= n["y1"] <= 700 and not company:
                # Company adalah baris kecil sebelum title besar
                if (n["y2"] - n["y1"]) < 80:
                    company = t
                    continue
            if 300 <= n["y1"] <= 1000 and not title and len(t) > 8:
                # Title biasanya text yang lebih panjang
                title = t
            if company and title:
                break
        return company, title
    except Exception:
        return "", ""


# ====================== FILTERS ======================

def _blacklisted(company):
    if not company:
        return False
    lo = company.lower()
    return any(b.lower() in lo for b in BLACKLIST_COMPANIES)


def _fuzzy(title):
    if not title:
        return True  # ga ada title -> jangan filter agresif
    lo = title.lower()
    return any(kw in lo for kw in FUZZY_KEYWORDS)


def _job_id(company, title):
    return f"linkedin:{(company or '').strip().lower()}:{(title or '').strip().lower()}"


# ====================== APPLY FLOW ======================

def _on_apply_form(d):
    try:
        return bool(d.xpath('//*[starts-with(@text,"Apply to ")]').wait(timeout=0.5))
    except Exception:
        return False


def _tap_button(d, label_patterns, timeout: float = 2.0):
    """Tap button by text. label_patterns = list str (case-insensitive partial match)."""
    for pat in label_patterns:
        try:
            node = d.xpath(f'//*[@text="{pat}" or contains(@content-desc,"{pat}")]')
            if node.wait(timeout=timeout):
                node.click()
                return True
        except Exception:
            pass
    return False


def _close_apply_form(d):
    """Close form via X di kiri atas. Konfirmasi 'Discard' jika muncul."""
    try:
        node = d.xpath('//*[@content-desc="Close" or @content-desc="Dismiss"]')
        if node.wait(timeout=1):
            node.click()
            time.sleep(T_ANIM)
    except Exception:
        pass
    # Confirm discard
    for label in ["Discard", "Yes", "Cancel applying"]:
        try:
            node = d.xpath(f'//*[@text="{label}"]')
            if node.wait(timeout=0.6):
                node.click()
                time.sleep(T_ANIM)
                return
        except Exception:
            pass


def _current_page_label(d):
    """Ambil label 'Page X of Y' untuk deteksi advance."""
    try:
        nodes = d.xpath('//*[contains(@text,"Page ") and contains(@text," of ")]').all()
        for n in nodes:
            t = n.attrib.get("text", "")
            m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", t)
            if m:
                return (int(m.group(1)), int(m.group(2)))
    except Exception:
        pass
    return None


def _find_unfilled_edittext(d):
    """Cari EditText kosong yang required. Return (node, label_str) atau (None, '')."""
    try:
        edits = d.xpath('//*[@class="android.widget.EditText"]').all()
        for e in edits:
            txt = e.attrib.get("text", "").strip()
            if txt:
                continue
            b = e.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            y_edit = int(m.group(2))
            label = ""
            tvs = d.xpath('//*[@text!=""]').all()
            best_dy = 999
            for tv in tvs:
                tvt = tv.attrib.get("text", "").strip()
                if not tvt or tv.attrib.get("class", "") == "android.widget.EditText":
                    continue
                tvb = tv.attrib.get("bounds", "")
                mm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", tvb)
                if not mm:
                    continue
                ty2 = int(mm.group(4))
                dy = y_edit - ty2
                if 0 < dy < best_dy and dy < 200:
                    best_dy = dy
                    label = tvt
            return (e, str(label))
    except Exception:
        pass
    return (None, "")


def _answer_unfilled(d):
    """Coba isi 1 EditText kosong via AI. Return True jika berhasil isi."""
    node, label = _find_unfilled_edittext(d)
    if not node:
        return False
    try:
        node.click()
        time.sleep(T_TAP)
        question = label or "Please describe your relevant experience."
        is_numeric = any(k in label.lower() for k in ["years", "year", "tahun", "salary", "gaji"])
        ans = ai_helper.answer_question(question, max_chars=300) or "3"
        if is_numeric and not re.search(r"\d", ans):
            ans = "3"
        safe = ans.replace(" ", "%s").replace("'", "").replace('"', "")[:300]
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "text", safe)
        time.sleep(T_TAP)
        # Dismiss keyboard
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_TAP)
        print(f"[linkedin]   isi '{label[:30]}' -> '{ans[:40]}'")
        return True
    except Exception as e:
        print(f"[linkedin]   gagal isi: {e}")
        return False


def _submit_flow(d, max_pages=10):
    """
    Loop: Next -> Next -> Review -> Submit.
    Return True jika berhasil submit, False jika abort.
    """
    last_page = None
    stuck_count = 0
    for step in range(max_pages):
        time.sleep(T_LOAD)
        cur_page = _current_page_label(d)

        # Cek apakah sudah di review/submit screen
        if d.xpath('//*[@text="Submit"]').wait(timeout=0.5):
            print(f"[linkedin]   submit ditekan (step {step})")
            d.xpath('//*[@text="Submit"]').click()
            time.sleep(T_LOAD + 1)
            return True

        # Detect stuck (page label tidak berubah)
        if cur_page and last_page and cur_page == last_page:
            stuck_count += 1
            print(f"[linkedin]   stuck page {cur_page}, try fill...")
            filled = _answer_unfilled(d)
            if not filled:
                if stuck_count >= 2:
                    print(f"[linkedin]   abort: stuck > 2x di page {cur_page}")
                    return False
        else:
            stuck_count = 0

        last_page = cur_page

        # Tap Next / Review (button di bottom right)
        if _tap_button(d, ["Review"], timeout=0.4):
            print(f"[linkedin]   review ditekan")
            continue
        if _tap_button(d, ["Next", "Continue"], timeout=0.4):
            continue

        # Tidak ada button -> mungkin error
        print(f"[linkedin]   no advance button found di step {step}")
        return False

    return False


def _dismiss_post_apply(d):
    """Setelah submit, dismiss 'show open to work' / close confirmation."""
    for label in ["No thanks", "Done", "Close", "Maybe later", "Not now"]:
        try:
            node = d.xpath(f'//*[@text="{label}" or @content-desc="{label}"]')
            if node.wait(timeout=1):
                node.click()
                time.sleep(T_ANIM)
                break
        except Exception:
            pass
    # Close X button di post-apply hub
    try:
        node = d.xpath('//*[@resource-id="com.linkedin.android:id/post_apply_hub_close_button"]')
        if node.wait(timeout=0.6):
            node.click()
            time.sleep(T_ANIM)
    except Exception:
        pass


def _apply_to_card(d, tap_y):
    """
    Tap card di y=tap_y, baca title+company dari detail page,
    cek filter (state/blacklist/fuzzy/page-count), klik Easy Apply, complete form.
    Return (success: bool, company: str, title: str).
    """
    adb_utils.adb(DEVICE_SERIAL, "shell", "input", "tap", "540", str(tap_y))
    time.sleep(T_LOAD + 1)

    company, title = _read_detail_title_company(d)
    if not title:
        print(f"[linkedin]   no title detected, skip")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, "", ""

    jid = _job_id(company, title)
    if jid in _seen:
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title
    _seen.add(jid)

    if state_manager.is_applied(jid):
        print(f"[linkedin]   skip (state) {company} | {title}")
        _track_skip(company, title, "state")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title
    if _blacklisted(company):
        print(f"[linkedin]   skip (blacklist) {company}")
        _track_skip(company, title, "blacklist")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title
    if not _fuzzy(title):
        print(f"[linkedin]   skip (fuzzy) {title}")
        _track_skip(company, title, "fuzzy-mismatch")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title

    print(f"[linkedin]   APPLY {company} | {title}")

    if not _tap_button(d, ["Easy Apply"], timeout=2.5):
        print(f"[linkedin]   no Easy Apply button, skip")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title

    time.sleep(T_LOAD + 1)
    if not _on_apply_form(d):
        print(f"[linkedin]   form tidak terbuka")
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title

    # Cek page count. Job dengan > 4 pages biasanya punya banyak pertanyaan,
    # auto-fill kita belum reliable -> skip biar tidak terjebak.
    page_info = _current_page_label(d)
    if page_info and page_info[1] > 4:
        print(f"[linkedin]   skip: form punya {page_info[1]} pages (>4)")
        _close_apply_form(d)
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title

    ok = _submit_flow(d)
    if not ok:
        _close_apply_form(d)
        adb_utils.adb(DEVICE_SERIAL, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(T_ANIM)
        return False, company, title

    _dismiss_post_apply(d)
    _goto_jobs_tab(d)
    return True, company, title


# ====================== MAIN ENTRY ======================

def run_batch(d, limit=BATCH_SIZE):
    """
    Run satu giliran LinkedIn. Return jumlah lamaran berhasil.
    """
    global _seen

    _launch_fresh(d)
    time.sleep(T_LAUNCH)

    if not _goto_jobs_tab(d):
        print("[linkedin] gagal navigasi ke Jobs tab")
        return 0

    applied = 0
    scroll_attempts = 0
    max_scrolls = 6

    tried_tap_ys = set()

    while applied < limit and scroll_attempts < max_scrolls:
        cards = _get_visible_cards(d)
        new_cards = [c for c in cards if c["tap_y"] not in tried_tap_ys]
        if not new_cards:
            _scroll_jobs(d)
            scroll_attempts += 1
            continue

        for card in new_cards:
            if applied >= limit:
                break
            tried_tap_ys.add(card["tap_y"])
            ok, company, title = _apply_to_card(d, card["tap_y"])
            if ok:
                jid = _job_id(company, title)
                state_manager.mark_applied(jid)
                report.write_application(
                    platform="LinkedIn",
                    company=company,
                    position=title,
                    salary_min=0, salary_max=0,
                    notes="Easy Apply via LinkedIn Top picks",
                    description="",
                )
                applied += 1
                print(f"[linkedin] ({applied}/{limit}) {company} | {title}")
                time.sleep(T_LOAD)

    print(f"[linkedin] batch done: {applied} apply, scroll {scroll_attempts}x")
    return applied
