DEVICE_SERIAL = "13344254B7000215"

GLINTS_PACKAGE  = "com.glints.candidate"
GLINTS_ACTIVITY = "com.glints.candidate/.MainActivity"

JOBSTREET_PACKAGE  = "com.jobstreet.jobstreet"
JOBSTREET_ACTIVITY = "com.jobstreet.jobstreet/seek.base.deeplink.presentation.DeeplinkActivity"

REPORT_DIR = r"C:\Users\Engineer02\Desktop\persona\Lamaran"
STATE_FILE  = r"C:\Users\Engineer02\Desktop\persona\automation\state.json"
PROFILE_FILE = r"C:\Users\Engineer02\Desktop\persona\profile\yoel_profile.json"

# Kecepatan — agresif maksimal
T_TAP     = 0.15  # jeda setelah tap biasa
T_ANIM    = 0.35  # jeda setelah transisi / animasi
T_LOAD    = 1.0   # jeda tunggu halaman load
T_LAUNCH  = 3.0   # jeda setelah launch app

BATCH_SIZE = 5    # jumlah lamaran per giliran per app

BLACKLIST_COMPANIES = [
    "PT Gemilang Satria Perkasa", "Gemilang Satria Perkasa", "PT. GSP",
    "Zando Agency", "Zando", "Eka Agency",
    "PT ADIDAYA RISET INSTRUMEN INDONESIA", "ADIDAYA RISET",
]

FUZZY_KEYWORDS = [
    # AI / ML / Agentic - core profile Yoel
    "ai", "artificial intelligence", "machine learning", "ml ", "llm",
    "deep learning", "nlp", "agentic", "agent ai", "ai agent",
    "ai engineer", "ai developer", "ai specialist", "ai consultant",
    "prompt engineer", "rag ", "vector",
    "computer vision", "mlops",
    "generative ai", "gen ai", "genai",
    # Data Engineering only (pipelines/backend) — NO data scientist/analyst/BI (off-fit)
    "data engineer",
    # Frontend
    "frontend", "front end", "front-end", "react", "reactjs", "next js",
    "nextjs", "next.js", "vue", "vuejs", "angular", "typescript",
    "ui developer", "ui engineer", "ux engineer",
    # Backend
    "backend", "back end", "back-end", "fastapi", "node", "nodejs", "node.js",
    "python developer", "django developer", "flask developer",
    # Fullstack
    "full stack", "fullstack", "full-stack",
    # Software / Web
    "software engineer", "software developer", "web developer", "programmer",
    "web engineer",
    # IT
    "it support", "it specialist", "it engineer", "tech support",
    "helpdesk", "help desk", "system engineer",
    # DevOps / Cloud / Infra
    "devops", "cloud engineer", "platform engineer", "site reliability",
    "sre", "infrastructure engineer",
    # Blockchain / web3 (CV: VeChain, Solidity, Hardhat)
    "blockchain", "smart contract", "solidity", "web3", "dapp", "dapp developer",
    # Mobile
    "mobile developer", "android developer", "ios developer",
    "react native",
]

MIN_SALARY = 8_000_000
