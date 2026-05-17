import os
import json
import urllib.request
import urllib.error

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

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


def _static_answer(question: str) -> str:
    """Fallback: jawaban statis berbasis keyword dari pertanyaan."""
    q = question.lower()

    if any(k in q for k in ["year", "tahun", "experience", "pengalaman"]):
        if any(k in q for k in ["python", "machine learning", "ai", "data"]):
            return "3 years. I have been working with Python for AI and machine learning projects since 2022, building production systems including LangGraph agents, LLM pipelines, and data processing tools for national-scale government AI infrastructure."
        return "3 years of professional experience in software engineering and AI development."

    if any(k in q for k in ["why", "mengapa", "kenapa", "alasan", "reason", "interest", "tertarik"]):
        return "I am deeply passionate about AI engineering and have built production-grade agentic systems. This role aligns perfectly with my expertise in LangGraph, Python, and full-stack development. I want to contribute to impactful products at scale."

    if any(k in q for k in ["skill", "keahlian", "kemampuan", "ability", "proficient"]):
        return "Proficient in Python, LangGraph, LangChain, FastAPI, Docker, Vue 3, React, PostgreSQL, Redis, and cloud infrastructure. I specialize in agentic AI architecture and full-stack development."

    if any(k in q for k in ["salary", "gaji", "ekspektasi", "expectation"]):
        return "10000000"

    if any(k in q for k in ["available", "mulai", "start", "kapan", "when"]):
        return "I am available immediately."

    if any(k in q for k in ["strength", "kelebihan", "kekuatan"]):
        return "My strength is building complex AI systems from zero to production. I have delivered national-scale infrastructure under tight deadlines with a small team, demonstrating both technical depth and execution speed."

    if any(k in q for k in ["weakness", "kelemahan", "kekurangan"]):
        return "I tend to be a perfectionist with technical quality, but I manage this by setting clear milestones and communicating early with stakeholders to ensure timely delivery."

    if any(k in q for k in ["describe", "ceritakan", "tell", "jelaskan"]):
        return "I am an AI Forward Deployed Engineer with 3 years of experience building production AI systems, including national-scale multi-agent infrastructure for Indonesian government agencies using LangGraph, Python, and Docker."

    # Generic fallback
    return "I have extensive experience in this area through my work building AI systems and software applications. I am confident I can contribute effectively to this role based on my technical background and track record of delivering production-grade solutions."
