import os
import json
import urllib.request
import urllib.error

from dotenv import load_dotenv

# Load .env dari root project (parent dari automation/).
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
BASE_URL = f"{OPENROUTER_BASE}/chat/completions"

if not OPENROUTER_API_KEY:
    print(f"[ai] WARNING: OPENROUTER_API_KEY tidak ter-load dari {_ENV_PATH}")

# Free models — diambil live dari /api/v1/models (Q1 2026 / Mei 2026).
# Urut prioritas: kualitas tinggi -> fallback ringan.
FREE_MODELS = [
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "z-ai/glm-4.5-air:free",
    "deepseek/deepseek-v4-flash:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]

PROFILE_SUMMARY = """
Name: Yoel Andreas Manoppo
Title: AI Forward Deployed Engineer, Agentic AI Architecture, UI Specialist
Experience: 3 years in tech (since 2022)

Work History:
- AI Forward Deployed Engineer at PT. GSP (May 2025 - present): Built national-scale multi-agent AI for Indonesian government (BNPT, Bareskrim). LangGraph, Python, Docker, Prometheus, Grafana, ChromaDB.
- Software Engineer at PT. Decision Tree Indonesia (Dec 2024 - present): Enterprise dashboard Next.js, PostgreSQL, Redis, BullMQ.
- Lead dApp Developer (CTO) at VeChain Ecosystem (Jan 2024 - Feb 2026): Greencart dApp with 1 million users, AI OCR pipeline, Solidity, Hardhat.
- AI Specialist at Zando Agency (May 2022 - Dec 2024): Fine-tuned local LLMs, automated workflows, virtual AI influencers.

Key Skills: LangGraph, LangChain, Ollama, OpenAI, Groq, Whisper, Python, FastAPI, PostgreSQL, Redis, Docker, Vue 3, TypeScript, React, Next.js, TailwindCSS, Prometheus, Grafana, Langfuse, ChromaDB, VeChain, Solidity.

Education: B.Sc. Business Administration (University of the People), Harvard CS50, EFSET C2 English.
Languages: Indonesian (native), English (C2), Mandarin (conversational).
Salary expectation: Rp 10.000.000 per month.
Available: immediately.
"""

SYSTEM_PROMPT = f"""You are answering job application questions on behalf of Yoel Andreas Manoppo.
Answer concisely, professionally, and truthfully based on his profile below.
Keep answers under 400 characters unless the question explicitly asks for more detail.
Write in the same language as the question (English or Indonesian).
Do not use markdown, bullet points, or special characters. Plain text only.

PROFILE:
{PROFILE_SUMMARY}"""


_SUMMARY_SYSTEM_PROMPT = """You are a hiring assistant analyzing a job posting Yoel just applied to.
Your job: produce a clean, well-structured Indonesian markdown report from the raw scraped text.
Read the text carefully and infer what you can about the company culture, industry, role, and fit.
Always write in Bahasa Indonesia. Use the exact section headers below."""


def summarize_job(raw_text: str, company: str, position: str) -> str:
    """
    Buat summary terstruktur perusahaan + role dalam markdown Indonesia
    dari raw text yang di-scrape dari halaman detail job (Glints/JS/LinkedIn).
    Output langsung di-embed ke laporan harian.
    """
    raw_text = (raw_text or "").strip()[:4000]  # cap input
    if not raw_text or len(raw_text) < 50:
        return ""

    user_prompt = f"""Berikut raw text hasil scrape dari halaman lowongan kerja:

==== RAW TEXT ====
{raw_text}
==================

Posisi: {position}
Perusahaan: {company}

Profile pelamar:
{PROFILE_SUMMARY}

Tulis laporan markdown ringkas tapi informatif (max 600 kata, Bahasa Indonesia, JANGAN pakai emoji) dengan struktur EXACT:

**Tentang Perusahaan**
- Industri: ...
- Lokasi: ...
- Ukuran tim: ... (kalau ada info)
- Kultur / vibe: ... (infer dari tone teks, benefit, tunjangan)

**Tentang Role**
2-4 kalimat menjelaskan tanggung jawab utama dengan jelas.

**Skill / Requirement Utama**
- 4-6 bullet skill paling penting yang diminta

**Benefit & Tunjangan**
- 3-6 bullet (kalau disebutkan di raw text saja, jangan karang)

**Cocok untuk Yoel?**
2 kalimat: hubungkan profile Yoel dengan role ini, dan flag concern kalau ada (misalnya lokasi luar Jakarta, gaji bawah ekspektasi, skill jauh dari core).

Aturan: jangan pakai placeholder seperti "tidak disebutkan". Kalau info tidak ada di raw text, skip bullet itu. Jangan tambahkan judul lain di luar 5 section di atas. Plain markdown, tanpa code block."""

    for model in FREE_MODELS:
        try:
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 900,
                "temperature": 0.3,
            }).encode("utf-8")

            req = urllib.request.Request(
                BASE_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Y0EL",
                    "X-Title": "Yoel Job Apply Bot",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                summary = data["choices"][0]["message"]["content"].strip()
                print(f"[ai] summary via {model.split('/')[0]} -> {len(summary)} chars")
                return summary
        except Exception as e:
            print(f"[ai] summary model {model} gagal: {e}")
            continue
    return ""


_RETRO_SYSTEM_PROMPT = """You are a career coach reviewing Yoel's job-application session.
Job: write an honest Indonesian markdown retrospective for one job platform that just finished its session.
Lead with data, end with actionable improvement. Bahasa Indonesia, no emoji, plain markdown."""


def platform_retrospective(platform: str, applied: int, skip_counters: dict | None = None,
                            sample_skipped: list | None = None) -> str:
    """
    Generate markdown retrospective untuk satu platform yang selesai.
    `skip_counters` = dict reason->count, mis. {'state': 80, 'fuzzy': 12, 'gaji': 5}.
    `sample_skipped` = list of (company, position, reason) — sample 5-10 lowongan.
    """
    skip_counters = skip_counters or {}
    sample_skipped = sample_skipped or []

    skip_summary = ""
    if skip_counters:
        skip_summary = "Alasan skip:\n" + "\n".join(
            f"- {reason}: {cnt}" for reason, cnt in sorted(
                skip_counters.items(), key=lambda x: -x[1]
            )
        )

    sample_summary = ""
    if sample_skipped:
        sample_summary = "Contoh lowongan yang muncul tapi di-skip:\n" + "\n".join(
            f"- [{r}] {c} — {p}"[:200] for c, p, r in sample_skipped[:10]
        )

    user_prompt = f"""Platform {platform} sudah tidak ada lowongan baru untuk Yoel hari ini.

Data session:
- Total lowongan ter-apply hari ini di {platform}: {applied}
{skip_summary}

{sample_summary}

Profile Yoel (untuk konteks rekomendasi):
{PROFILE_SUMMARY}

Tulis section markdown dengan struktur EXACT (jangan ubah judul):

**Mengapa {platform} Sudah Selesai Hari Ini**
2-3 kalimat: jelaskan kondisi (saturasi state, fuzzy mismatch, gaji bawah threshold, blacklist, dll) — pakai angka skip-counter di atas kalau ada.

**Pola Lowongan yang Muncul tapi Di-skip**
3-5 bullet: identifikasi pattern dari lowongan yang di-skip (industri, level, lokasi, gaji, skill yang sering muncul). Pakai sample di atas kalau membantu.

**Rekomendasi Improvement untuk Yoel**
4-6 bullet konkret:
- Skill / sertifikasi yang sering diminta perusahaan di {platform} tapi belum ada di profile Yoel — sebutkan eksplisit
- Adjustment ekspektasi (lokasi, gaji, level role) kalau filter terlalu sempit
- Profile / CV upgrade untuk naikin call-back rate (mis. portfolio item, achievement quantification, headline keyword)
- Strategi besok: keyword baru yang bisa di-explore atau platform alternatif

Aturan: max 450 kata, plain markdown, tidak pakai emoji, tidak pakai code block. Mulai langsung dari `**Mengapa...**`, jangan ada preamble."""

    for model in FREE_MODELS:
        try:
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": _RETRO_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 800,
                "temperature": 0.4,
            }).encode("utf-8")

            req = urllib.request.Request(
                BASE_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Y0EL",
                    "X-Title": "Yoel Job Apply Bot",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                summary = data["choices"][0]["message"]["content"].strip()
                print(f"[ai] retrospective {platform} via {model.split('/')[0]} -> {len(summary)} chars")
                return summary
        except Exception as e:
            print(f"[ai] retrospective {platform} model {model} gagal: {e}")
            continue
    return ""


def answer_question(question: str, max_chars: int = 400) -> str:
    """
    Generate a contextual answer for a job application question
    using Yoel's profile via OpenRouter free model.
    Falls back to a static smart answer if API fails.
    """
    for model in FREE_MODELS:
        try:
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Answer this job application question:\n\n{question}"},
                ],
                "max_tokens": 200,
                "temperature": 0.4,
            }).encode("utf-8")

            req = urllib.request.Request(
                BASE_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Y0EL",
                    "X-Title": "Yoel Job Apply Bot",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answer = data["choices"][0]["message"]["content"].strip()
                answer = answer[:max_chars]
                print(f"[ai] Model {model.split('/')[0]} -> {answer[:60]}...")
                return answer

        except Exception as e:
            print(f"[ai] Model {model} gagal: {e}")
            continue

    # Fallback static jika semua model gagal
    return _static_answer(question)


def _is_indonesian(text: str) -> bool:
    """Deteksi bahasa kasar: kata Indonesia umum."""
    t = text.lower()
    return any(w in t for w in [
        "apakah", "anda", "bersedia", "berapa", "mengapa", "kenapa",
        "jelaskan", "ceritakan", "alasan", "tahun", "pengalaman", "saya",
        "kamu", "bagaimana", "bisa kah", "bisakah", "dapat", "siap",
    ])


def _is_yes_no(q: str) -> bool:
    """
    Yes/No question detection.
    Indicator kuat: "apakah ...", "bersedia", "willing to", "are you able",
    "do you have", "can you", "have you", "would you", "available to",
    "bisa/dapat/siap/mau ... ?"
    """
    qs = q.strip().lower()
    if not qs.endswith("?"):
        # Kadang content-desc gak punya "?" tapi tetap yes/no
        pass
    yn_patterns = [
        "apakah ", "apakah anda", "apakah kamu", "bersedia",
        "are you willing", "willing to", "are you able", "able to",
        "do you have", "have you", "can you", "could you", "would you",
        "are you available", "available to", "are you comfortable",
        "are you ok with", "are you open to",
        "bisakah", "dapatkah", "maukah", "siapkah", "sudahkah",
    ]
    return any(p in qs for p in yn_patterns)


def _yes_no_answer(q: str) -> str:
    """Jawaban Yes/No yang singkat + alasan satu kalimat, sesuai bahasa."""
    qs = q.lower()
    id_mode = _is_indonesian(q)

    # Default: YA (Yoel terbuka & fleksibel untuk hampir semua kondisi kerja)
    # Tweak singkat berdasarkan konteks pertanyaan.

    if any(k in qs for k in ["on-site", "on site", "onsite", "wfo", "kantor", "office"]):
        return ("Ya, saya bersedia bekerja full on-site sesuai jadwal perusahaan."
                if id_mode else
                "Yes, I am fully willing to work on-site per company schedule.")

    if any(k in qs for k in ["remote", "wfh", "work from home", "dari rumah"]):
        return ("Ya, saya bersedia bekerja remote dan terbiasa dengan tools kolaborasi seperti Slack, Notion, dan Git."
                if id_mode else
                "Yes, I am comfortable working remotely and used to async collaboration via Slack, Notion, and Git.")

    if any(k in qs for k in ["hybrid"]):
        return ("Ya, saya bersedia dengan skema hybrid."
                if id_mode else
                "Yes, I am comfortable with a hybrid arrangement.")

    if any(k in qs for k in ["shift", "malam", "weekend", "lembur", "overtime", "night"]):
        return ("Ya, saya fleksibel dengan jam kerja termasuk shift atau lembur ketika dibutuhkan."
                if id_mode else
                "Yes, I am flexible with shift schedules and overtime when needed.")

    if any(k in qs for k in ["relocate", "pindah", "domisili", "lokasi", "location"]):
        return ("Ya, saya bersedia relokasi jika dibutuhkan; saat ini berdomisili di Jakarta."
                if id_mode else
                "Yes, I am open to relocation if needed; currently based in Jakarta.")

    if any(k in qs for k in ["travel", "perjalanan", "dinas"]):
        return ("Ya, saya bersedia melakukan perjalanan dinas sesuai kebutuhan."
                if id_mode else
                "Yes, I am willing to travel for business as needed.")

    if any(k in qs for k in ["mulai", "join", "start", "available immediately", "segera"]):
        return ("Ya, saya bisa mulai segera (immediate)."
                if id_mode else
                "Yes, I am available to start immediately.")

    if any(k in qs for k in ["kontrak", "freelance", "part time", "part-time", "contract"]):
        return ("Ya, saya bersedia dengan skema kontrak/freelance sesuai kesepakatan."
                if id_mode else
                "Yes, I am open to contract or freelance arrangements per agreement.")

    if any(k in qs for k in ["bahasa inggris", "english", "berbahasa", "english proficiency"]):
        return ("Ya, saya fasih berbahasa Inggris (EFSET C2)."
                if id_mode else
                "Yes, I am fluent in English (EFSET C2).")

    if any(k in qs for k in ["python", "javascript", "react", "node", "docker", "sql",
                              "postgres", "linux", "git", "aws", "gcp", "azure"]):
        return ("Ya, saya menguasai tools tersebut dan sudah pakai di production."
                if id_mode else
                "Yes, I have hands-on production experience with that tool.")

    # Generic Yes
    return ("Ya, saya bersedia."
            if id_mode else
            "Yes, I am.")


def _static_answer(question: str) -> str:
    """Fallback: jawaban statis berbasis keyword dari pertanyaan."""
    q = question.lower()

    # 0. Yes/No DULU sebelum branch lain — supaya "Apakah bersedia..." tidak
    #    ke-fallback ke generic essay.
    if _is_yes_no(question):
        return _yes_no_answer(question)

    id_mode = _is_indonesian(question)

    if any(k in q for k in ["year", "tahun", "experience", "pengalaman"]):
        if any(k in q for k in ["python", "machine learning", "ai", "data"]):
            return ("3 tahun. Saya mengerjakan Python untuk AI dan machine learning sejak 2022, membangun production system termasuk LangGraph agents, LLM pipeline, dan data processing untuk infrastruktur AI pemerintah Indonesia."
                    if id_mode else
                    "3 years. I have been working with Python for AI and machine learning projects since 2022, building production systems including LangGraph agents, LLM pipelines, and data processing tools for national-scale government AI infrastructure.")
        return ("3 tahun pengalaman profesional di software engineering dan AI development."
                if id_mode else
                "3 years of professional experience in software engineering and AI development.")

    if any(k in q for k in ["why", "mengapa", "kenapa", "alasan", "reason", "interest", "tertarik"]):
        return ("Saya passionate di bidang AI engineering dan sudah membangun production-grade agentic system. Role ini cocok dengan keahlian saya di LangGraph, Python, dan full-stack development. Saya ingin berkontribusi pada produk yang berdampak skala besar."
                if id_mode else
                "I am deeply passionate about AI engineering and have built production-grade agentic systems. This role aligns perfectly with my expertise in LangGraph, Python, and full-stack development. I want to contribute to impactful products at scale.")

    if any(k in q for k in ["skill", "keahlian", "kemampuan", "ability", "proficient"]):
        return ("Menguasai Python, LangGraph, LangChain, FastAPI, Docker, Vue 3, React, PostgreSQL, Redis, dan cloud infrastructure. Spesialisasi saya di agentic AI architecture dan full-stack development."
                if id_mode else
                "Proficient in Python, LangGraph, LangChain, FastAPI, Docker, Vue 3, React, PostgreSQL, Redis, and cloud infrastructure. I specialize in agentic AI architecture and full-stack development.")

    if any(k in q for k in ["salary", "gaji", "ekspektasi", "expectation"]):
        return "10000000"

    if any(k in q for k in ["available", "mulai", "start", "kapan", "when"]):
        return ("Saya bisa mulai segera (immediate)."
                if id_mode else
                "I am available immediately.")

    if any(k in q for k in ["strength", "kelebihan", "kekuatan"]):
        return ("Kekuatan saya adalah membangun sistem AI kompleks dari nol ke production. Saya sudah deliver infrastruktur skala nasional dengan deadline ketat dan tim kecil."
                if id_mode else
                "My strength is building complex AI systems from zero to production. I have delivered national-scale infrastructure under tight deadlines with a small team, demonstrating both technical depth and execution speed.")

    if any(k in q for k in ["weakness", "kelemahan", "kekurangan"]):
        return ("Saya cenderung perfectionist soal kualitas teknis, tapi saya manage dengan set milestone yang jelas dan komunikasi awal ke stakeholder untuk pastikan delivery tepat waktu."
                if id_mode else
                "I tend to be a perfectionist with technical quality, but I manage this by setting clear milestones and communicating early with stakeholders to ensure timely delivery.")

    if any(k in q for k in ["describe", "ceritakan", "tell", "jelaskan"]):
        return ("Saya AI Forward Deployed Engineer dengan 3 tahun pengalaman membangun production AI system, termasuk infrastruktur multi-agent skala nasional untuk pemerintah Indonesia menggunakan LangGraph, Python, dan Docker."
                if id_mode else
                "I am an AI Forward Deployed Engineer with 3 years of experience building production AI systems, including national-scale multi-agent infrastructure for Indonesian government agencies using LangGraph, Python, and Docker.")

    # Generic fallback
    return ("Saya punya pengalaman relevan di bidang ini melalui pekerjaan membangun AI system dan aplikasi software. Saya yakin dapat berkontribusi efektif untuk role ini berdasarkan track record delivery production-grade solution."
            if id_mode else
            "I have extensive experience in this area through my work building AI systems and software applications. I am confident I can contribute effectively to this role based on my technical background and track record of delivering production-grade solutions.")
