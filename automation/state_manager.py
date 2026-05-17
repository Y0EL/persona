import json
import os
from config import STATE_FILE


def load():
    if not os.path.exists(STATE_FILE):
        return {"jobstreet_logged_in": False, "applied_jobs": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_applied(job_id):
    state = load()
    return job_id in state.get("applied_jobs", [])


def mark_applied(job_id):
    state = load()
    applied = state.get("applied_jobs", [])
    if job_id not in applied:
        applied.append(job_id)
    state["applied_jobs"] = applied
    save(state)


def set_jobstreet_logged_in(value=True):
    state = load()
    state["jobstreet_logged_in"] = value
    save(state)


def jobstreet_logged_in():
    return load().get("jobstreet_logged_in", False)
