# -*- coding: utf-8 -*-
"""StudyBot AI - Engineering-ready study planner (Streamlit, standalone)."""
import os, re, json, time, copy, hashlib, secrets
from datetime import datetime, date, timedelta
import requests
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
try:
    from dotenv import load_dotenv
    for _p in (os.path.join(BASE, ".env"), os.path.join(os.path.dirname(BASE), ".env")):
        if os.path.exists(_p):
            load_dotenv(_p)
except Exception:
    pass
DATA_PATH = os.path.join(BASE, "studybot_data.json")
F = "%Y-%m-%d"
KINDS = ["Assignment", "Unit test", "Pre-board / Mock test", "Lab record", "Practical", "Viva",
         "Internal / CA", "Mid-sem", "Project", "Other"]
STAT = ["Pending", "In progress", "Done"]
BRANCHES = ["CSE", "IT", "ECE", "EEE", "Mechanical", "Civil", "Chemical", "Other"]
CATEGORIES = ["Class 6-9 School", "Class 10 Board", "Class 12 Board", "Competitive Exam",
              "Engineering (College Sem)", "Other"]
BOARDS = ["CBSE", "ICSE/ISC", "UP Board", "Maharashtra", "Bihar", "Rajasthan", "MP Board", "Gujarat",
          "West Bengal", "Other State Board"]
STREAMS = ["Science (PCM)", "Science (PCB)", "Science (PCMB)", "Commerce", "Arts / Humanities"]
COMP_EXAMS = ["JEE Main", "JEE Advanced", "NEET UG", "NEET PG", "CUET UG", "GATE", "CAT", "UPSC CSE",
              "SSC CGL", "SSC CHSL", "Banking (IBPS/SBI)", "RRB NTPC", "RRB Group D", "NDA", "CLAT",
              "State PSC", "CA Foundation", "Other"]
QTYPES = {  # label: (type, style hint)
    "MCQ": ("mcq", ""),
    "Numerical": ("numerical", ""),
    "Integer type (JEE)": ("numerical", "answer is a single integer/decimal number, JEE/NEET numerical style"),
    "Assertion-Reason": ("mcq", "Assertion (A) and Reason (R) format, standard 4 options"),
    "Case-based": ("mcq", "write a 2-3 line case/passage in the question first, then the question"),
    "Board short/long answer": ("theory", "board exam style 3-5 marks, with marking points"),
    "Theory / Derivation": ("theory", ""),
    "Code output": ("code", ""),
}

# ====================== LOGIC (pure python: notify.py executes this part) ======================
def default_data():
    return {"version": 2, "users": {}, "_user": None,
            "profile": {"name": "", "category": "Class 12 Board", "board": "CBSE", "stream": "Science (PCM)",
                        "cls": 9, "branch": "CSE", "semester": 3, "exam": "", "exam_date": "",
                        "language": "Hinglish", "hours": 3.0, "weak": [], "wake": "06:30",
                        "sleep": "23:00", "school": "09:00-16:00", "meals": "13:00-14:00, 20:00-21:00",
                        "fixed": ""},
            "syllabus": {}, "mastery": {}, "quiz_log": [], "chunks": [], "focus": [],
            "goals": {"focus_min": 60, "quiz_q": 10, "custom": []},
            "plan": {}, "tracker": [],
            "telegram": {"chat_id": "", "time": "07:00", "on": False},
            "whatsapp": {"phone": "", "apikey": "", "on": False},
            "sms": {"phone": "", "on": False}}

def exam_label(p):
    c = p.get("category", "")
    if c == "Engineering (College Sem)":
        return f"B.Tech {p.get('branch', 'CSE')} Sem {p.get('semester', 3)}"
    if c == "Class 10 Board":
        return f"Class 10 {p.get('board', 'CBSE')} Board"
    if c == "Class 12 Board":
        return f"Class 12 {p.get('board', 'CBSE')} Board ({p.get('stream', '')})"
    if c == "Class 6-9 School":
        return f"Class {p.get('cls', 9)} ({p.get('board', 'CBSE')})"
    return p.get("exam") or "Exam"

def exam_style(p):
    c, e = p.get("category", ""), (p.get("exam") or "").lower()
    if c in ("Class 10 Board", "Class 12 Board", "Class 6-9 School"):
        return "NCERT/board pattern (1/2/3/5 marks), concept + numerical + case-based"
    if c == "Engineering (College Sem)":
        return "university semester exam style"
    if "jee" in e:
        return "JEE level: conceptual + tricky numericals"
    if "neet" in e:
        return "NEET pattern, NCERT-based, statement/assertion style"
    if "upsc" in e or "psc" in e:
        return "UPSC prelims style: statement-based, elimination"
    return "objective competitive exam: speed + accuracy"

def ctx_str(p):
    return f"{exam_label(p)} - {exam_style(p)}"

def preset_subjects(p):
    c, e, s = p.get("category", ""), (p.get("exam") or "").lower(), p.get("stream", "")
    if c in ("Class 10 Board", "Class 6-9 School"):
        return "Maths, Science, Social Science, English, Hindi"
    if c == "Class 12 Board":
        for k, v in (("PCMB", "Physics, Chemistry, Maths, Biology, English"), ("PCB", "Physics, Chemistry, Biology, English"),
                     ("PCM", "Physics, Chemistry, Maths, English"),
                     ("Commerce", "Accountancy, Business Studies, Economics, English")):
            if k in s:
                return v
        return "History, Political Science, Geography, English"
    if c == "Engineering (College Sem)":
        return "Data Structures, DBMS, Engineering Maths"
    if c == "Competitive Exam":
        for k, v in (("jee", "Physics, Chemistry, Maths"), ("neet", "Physics, Chemistry, Biology"),
                     ("upsc", "History, Geography, Polity, Economy, Environment, Science & Tech, Current Affairs, CSAT"),
                     ("psc", "History, Geography, Polity, Economy, Current Affairs"),
                     ("bank", "Quant, Reasoning, English, General Awareness, Computer"),
                     ("cuet", "General Test, English, Domain Subject"), ("gate", "Engineering Maths, General Aptitude, Core Subject"),
                     ("nda", "Maths, General Ability"), ("clat", "English, Current Affairs, Legal Reasoning, Logical Reasoning, Quant"),
                     ("ca ", "Accounting, Business Laws, Quant Aptitude, Economics")):
            if k in e:
                return v
        if e.startswith("cat"):
            return "Quant, DILR, VARC"
        return "Quant, Reasoning, English, General Awareness"
    return ""

def default_qtypes(p):
    c, e = p.get("category", ""), (p.get("exam") or "").lower()
    if c in ("Class 10 Board", "Class 12 Board", "Class 6-9 School"):
        return ["MCQ", "Board short/long answer", "Case-based"]
    if c == "Engineering (College Sem)":
        return ["MCQ", "Numerical"]
    if "jee" in e:
        return ["MCQ", "Integer type (JEE)"]
    if "neet" in e:
        return ["MCQ", "Assertion-Reason"]
    return ["MCQ"]

USERS_PATH = os.path.join(BASE, "studybot_users.json")
MIGRATED_FLAG = os.path.join(BASE, "studybot_migrated.flag")

def user_path(u):
    return os.path.join(BASE, f"studybot_u_{hashlib.sha1(str(u).encode('utf-8')).hexdigest()[:12]}.json")

def load_users():
    for p in (USERS_PATH, DATA_PATH):
        try:
            with open(p, encoding="utf-8") as f:
                u = json.load(f)
            return u if p == USERS_PATH else (u.get("users") or {})
        except Exception:
            continue
    return {}

def save_users(u):
    tmp = USERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=1)
    os.replace(tmp, USERS_PATH)

def current_user():
    try:
        return st.session_state.get("auth")
    except Exception:
        return None

def _merge(d, raw):
    for k, v in raw.items():
        if k in ("profile", "goals", "telegram", "whatsapp", "sms") and isinstance(v, dict):
            d[k].update(v)
        elif k not in ("users", "_user"):
            d[k] = v

def load_data(user=None):
    """Separate data per user. Empty default when not logged in."""
    user = user or current_user()
    d = default_data()
    if not user:
        return d
    d["_user"] = user
    path = user_path(user)
    if not os.path.exists(path) and os.path.exists(DATA_PATH) and not os.path.exists(MIGRATED_FLAG):
        try:  # old single-file data goes to the first old user (or demo) who logs in
            with open(DATA_PATH, encoding="utf-8") as f:
                old = json.load(f)
            if user == "demo" or user in (old.get("users") or {}):
                _merge(d, old)
                save_data(d)
                with open(MIGRATED_FLAG, "w") as f:
                    f.write(str(user))
                return d
        except Exception:
            pass
    try:
        with open(path, encoding="utf-8") as f:
            _merge(d, json.load(f))
    except Exception:
        pass
    return d

def save_data(d):
    if not d.get("_user"):
        return
    path = user_path(d["_user"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt, hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120000).hex()

def today_str(now=None):
    return (now or datetime.now()).strftime(F)

def hm(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)

def fmt(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"

def parse_intervals(text):
    out = []
    for m in re.finditer(r"(\d{1,2}):(\d{2})\s*(?:-|–|to)\s*(\d{1,2}):(\d{2})([^\n,;]*)", text or ""):
        a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
        if b > a:
            out.append((a, b, m[5].strip()))
    return out

def days_to_exam(p, now=None):
    try:
        return (datetime.strptime(p.get("exam_date", ""), F).date() - (now or datetime.now()).date()).days
    except Exception:
        return None

def free_slots(p, after=0):
    wake, sleep = hm(p.get("wake", "06:30")), hm(p.get("sleep", "23:00"))
    if sleep <= wake:
        sleep = 1439
    sleep -= 30
    busy = sorted((a, b) for a, b, _ in parse_intervals(
        f"{p.get('school', '')}, {p.get('meals', '')}\n{p.get('fixed', '')}"))
    merged = []
    for a, b in busy:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    slots, cur = [], max(wake, after)
    for a, b in merged:
        if a > cur:
            slots.append((cur, a))
        cur = max(cur, b)
    if sleep > cur:
        slots.append((cur, sleep))
    return [(s, e) for s, e in slots if e - s >= 30]

def parse_syllabus(text):
    out = {}
    for line in (text or "").splitlines():
        if ":" in line:
            s, t = line.split(":", 1)
            topics = [x.strip() for x in re.split(r"[,;]", t) if x.strip()]
            if s.strip() and topics:
                out[s.strip()] = topics
    return out

def syllabus_text(d):
    return "\n".join(f"{s}: {', '.join(t)}" for s, t in d["syllabus"].items())

def topic_list(d):
    return [(s, t) for s, ts in d["syllabus"].items() for t in ts]

def staleness(rec, now=None):
    try:
        last = datetime.strptime(rec["last"], F).date()
        return min(((now or datetime.now()).date() - last).days / 14, 1.0)
    except Exception:
        return 1.0

def priority(d, subj, topic, now=None):
    key = f"{subj}::{topic}"
    p, rec = d["profile"], d["mastery"].get(key)
    v = 0.6 if (not rec or rec.get("n", 0) == 0) else (1 - rec["m"]) * 0.7 + staleness(rec, now) * 0.3
    if subj.lower() in [w.strip().lower() for w in p.get("weak", [])]:
        v *= 1.15
    dl = days_to_exam(p, now)
    if dl is not None and 0 <= dl <= 14:
        v *= 1.2
    pl = d.get("plan") or {}
    if pl.get("date") == today_str(now):
        for t in pl.get("tasks", []):
            if t.get("ref") == key:
                if t["status"] in ("missed", "skipped"):
                    v += 0.25
                elif t["status"] == "done":
                    v -= 0.35
    return v

def build_candidates(d, now, exclude=()):
    c = []
    for s, t in topic_list(d):
        ref = f"{s}::{t}"
        if ref not in exclude:
            c.append({"ref": ref, "subject": s, "topic": t, "kind": "study", "p": priority(d, s, t, now)})
    for it in d.get("tracker", []):
        if it.get("status") == "Done":
            continue
        try:
            days = (datetime.strptime(it["due"], F).date() - now.date()).days
        except Exception:
            continue
        ref = "item::" + it["id"]
        if days <= 3 and ref not in exclude:
            c.append({"ref": ref, "subject": it.get("subject", ""), "kind": "item",
                      "topic": f"📝 {it['kind']}: {it['title']}", "p": 1.0 - 0.1 * max(days, 0)})
    return sorted(c, key=lambda x: -x["p"])

def plan_refresh(d, now=None, force=False):
    """Mark missed tasks, then refill the remaining future slots by priority."""
    now = now or datetime.now()
    today, nm = today_str(now), now.hour * 60 + now.minute
    pl = d.get("plan") or {}
    if pl.get("date") != today:
        pl, force = {"date": today, "tasks": []}, True
    d["plan"] = pl
    changed = force
    for t in pl["tasks"]:
        if t["status"] == "pending" and t["end"] <= nm:
            t["status"], changed = "missed", True
    if not changed:
        return False
    keep = [t for t in pl["tasks"] if t["status"] != "pending" or t["start"] <= nm]
    cur = [t for t in keep if t["status"] == "pending"]
    done_min = sum(t["end"] - t["start"] for t in keep if t["status"] == "done")
    cap = int(float(d["profile"].get("hours", 3)) * 60) - done_min - sum(t["end"] - t["start"] for t in cur)
    after = ((nm + 4) // 5) * 5
    if cur:
        after = max(after, max(t["end"] for t in cur) + 10)
    new = []
    if cap >= 30:
        cands = build_candidates(d, now, exclude={t["ref"] for t in cur})
        used = set()
        for s, e in free_slots(d["profile"], after):
            t0 = s
            while e - t0 >= 30 and cap >= 30:
                c = next((c for c in cands if c["ref"] not in used), None)
                if not c:
                    break
                L = min(50, e - t0, cap)
                used.add(c["ref"])
                new.append({"id": secrets.token_hex(3), "start": t0, "end": t0 + L, "subject": c["subject"],
                            "topic": c["topic"], "kind": c["kind"], "ref": c["ref"], "status": "pending"})
                cap -= L
                t0 += L + 10
    pl["tasks"] = sorted(keep + new, key=lambda t: t["start"])
    return True

def set_task_status(d, tid, status):
    for t in d.get("plan", {}).get("tasks", []):
        if t["id"] == tid:
            t["status"] = status
            if status == "done" and t.get("kind") == "item":
                for it in d["tracker"]:
                    if "item::" + it["id"] == t["ref"] and it["status"] == "Pending":
                        it["status"] = "In progress"

def focus_by_day(d):
    out = {}
    for x in d["focus"]:
        out[x["date"]] = out.get(x["date"], 0) + x["min"]
    return out

def streak(d, now=None):
    days = {k for k, v in focus_by_day(d).items() if v > 0}
    day = (now or datetime.now()).date()
    if day.strftime(F) not in days:
        day -= timedelta(1)
    n = 0
    while day.strftime(F) in days:
        n += 1
        day -= timedelta(1)
    return n

def today_stats(d, now=None):
    t = today_str(now)
    return (sum(x["min"] for x in d["focus"] if x["date"] == t),
            sum(x["total"] for x in d["quiz_log"] if x["date"] == t))

def record_quiz(d, subj, topic, correct, total, qtype):
    key, today = f"{subj}::{topic}", today_str()
    rec = d["mastery"].get(key) or {"m": 0.5, "n": 0, "c": 0, "t": 0}
    acc = correct / total if total else 0
    rec["m"] = round(acc if rec["n"] == 0 else 0.7 * rec["m"] + 0.3 * acc, 3)
    rec["n"] += 1; rec["c"] += correct; rec["t"] += total; rec["last"] = today
    d["mastery"][key] = rec
    d["quiz_log"].append({"date": today, "subject": subj, "topic": topic, "correct": correct,
                          "total": total, "type": qtype})

def make_chunks(text, src, size=900, overlap=150):
    text, out, i = re.sub(r"\s+", " ", text).strip(), [], 0
    while i < len(text):
        out.append({"src": src, "text": text[i:i + size]})
        i += size - overlap
    return out

def retrieve(d, query, k=4):
    ch = d.get("chunks", [])
    if not ch:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        X = TfidfVectorizer(stop_words="english").fit_transform([c["text"] for c in ch] + [query])
        sims = cosine_similarity(X[-1], X[:-1])[0]
        return [ch[i] for i in sims.argsort()[::-1][:k] if sims[i] > 0]
    except Exception:
        return []

def gemini(prompt, temperature=0.4, json_out=False):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    # Gemini 3.x default me lamba 'thinking' karta hai (slow). Quiz/plan ke liye 'low' kaafi hai.
    cfg = {"temperature": temperature, "maxOutputTokens": 8192,
           "thinkingConfig": {"thinkingLevel": os.getenv("GEMINI_THINKING", "low")}}
    if json_out:
        cfg["responseMimeType"] = "application/json"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    last = "Gemini se jawab nahi mila."
    for attempt in range(4):
        try:
            r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                              json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg},
                              timeout=(10, 75))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            last = "Gemini ne time par jawab nahi diya (internet slow ho sakta hai)."
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
            cfg.pop("thinkingConfig")  # is model par ye setting nahi chalti, bina uske dobara
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"Gemini abhi busy hai ({r.status_code})."
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            if txt.strip():
                return txt
        except Exception:
            pass
        last = "Gemini ne khali jawab diya."
    raise RuntimeError(f"{last} Dobara try karo, ya sawal kam (3) karke dekho.")

def parse_json(txt):
    t = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        return json.loads(re.search(r"(\[.*\]|\{.*\})", t, re.S).group(1))

def gen_questions(d, subj, topic, labels, n, level):
    p = d["profile"]
    ctx = "\n".join(c["text"] for c in retrieve(d, f"{subj} {topic}", 3))[:3000]
    ctx_txt = ("Notes context:\n" + ctx) if ctx else ""
    styles = ", ".join(f"{l} [type={QTYPES[l][0]}{'; ' + QTYPES[l][1] if QTYPES[l][1] else ''}]" for l in labels)
    prompt = f"""You are an expert teacher for {exam_label(p)}. Exam style: {exam_style(p)}.
Subject: {subj}, Topic: {topic}, Difficulty: {level}.
Create {n} questions, rotating through these styles: {styles}.
Return only a JSON array, no extra text. Format of each item:
mcq: {{"type":"mcq","q":"..","options":["A","B","C","D"],"answer":0,"explain":".."}}
numerical: {{"type":"numerical","q":"with data","answer":12.5,"unit":"..","explain":"step-by-step solution"}}
theory: {{"type":"theory","q":"derive / explain / differentiate","model_answer":"key points","explain":".."}}
code: {{"type":"code","q":"code snippet + what will the output be?","answer":"exact output","explain":".."}}
Questions in English, explanations in {p['language']}. Keep every explanation under 50 words. {ctx_txt}"""
    raw = parse_json(gemini(prompt, 0.5, True))
    out = []
    for it in raw if isinstance(raw, list) else []:
        t = str(it.get("type", "")).lower()
        it["type"] = t
        if not it.get("q"):
            continue
        if t == "mcq":
            o, a = it.get("options"), it.get("answer")
            if isinstance(o, list) and len(o) >= 2 and isinstance(a, int) and 0 <= a < len(o):
                out.append(it)
        elif t in ("numerical", "theory", "code"):
            out.append(it)
    if not out:
        raise RuntimeError("Could not generate valid questions. Please try again.")
    return out

NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

def grade_item(item, ans):
    t = item["type"]
    if ans in (None, ""):
        return False, "No answer given."
    if t == "mcq":
        return ans == item["options"][item["answer"]], ""
    if t == "numerical":
        try:
            g = float(re.findall(NUM, str(ans).replace(",", ""))[0])
            a = float(re.findall(NUM, str(item["answer"]).replace(",", ""))[0])
            return abs(g - a) <= max(abs(a) * 0.02, 1e-6), f"Correct answer: {item['answer']} {item.get('unit', '')}"
        except Exception:
            return False, ""
    if t == "code":
        n = lambda s: re.sub(r"\s+", "", str(s)).lower()
        return n(ans) == n(item.get("answer", "")), f"Correct output: {item.get('answer', '')}"
    try:
        r = parse_json(gemini(f"Question: {item['q']}\nModel answer: {item.get('model_answer', '')}\n"
                              f"Student answer: {ans}\nReturn JSON: {{\"score\":0-10,\"feedback\":\"1-2 lines\"}}",
                              0.2, True))
        sc = float(r["score"])
        return sc >= 6, f"AI score {sc:g}/10 - {r.get('feedback', '')}"
    except Exception as e:
        return False, f"AI check failed: {e}"

def send_telegram(text, chat_id=None, token=None, d=None):
    """chat_id can hold one or more IDs (separated by comma / space / new line)."""
    token = token or os.getenv("TELEGRAM_TOKEN")
    chat_id = chat_id or (d or load_data())["telegram"].get("chat_id")
    ids = [x for x in re.split(r"[,\s;]+", str(chat_id or "")) if x]
    if not token or not ids:
        return False, "TELEGRAM_TOKEN or chat id missing"
    fails, okn = [], 0
    for cid in ids:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": cid, "text": text[:4000]}, timeout=20)
            if r.status_code == 200:
                okn += 1
            else:
                fails.append(f"{cid}: {r.text[:120]}")
        except Exception as e:
            fails.append(f"{cid}: {e}")
    if fails:
        return False, f"{okn}/{len(ids)} sent. Failed -> " + " | ".join(fails)
    return True, f"{okn}/{len(ids)} sent"

def send_whatsapp(text, d=None):
    """Free WhatsApp via CallMeBot (unofficial, personal number only)."""
    w = (d or load_data()).get("whatsapp", {})
    if not w.get("phone") or not w.get("apikey"):
        return False, "WhatsApp phone or API key missing"
    try:
        r = requests.get("https://api.callmebot.com/whatsapp.php",
                         params={"phone": re.sub(r"[^\d]", "", w["phone"]), "text": text[:1500], "apikey": w["apikey"]},
                         timeout=30)
        return r.status_code == 200, r.text[:200]
    except Exception as e:
        return False, str(e)

def send_sms(text, phone=None, d=None):
    """Fast2SMS (India). API key in .env as FAST2SMS_KEY. Quick SMS route."""
    key = os.getenv("FAST2SMS_KEY")
    phone = phone or (d or load_data()).get("sms", {}).get("phone", "")
    nums = ",".join(n for n in (re.sub(r"\D", "", x)[-10:] for x in re.split(r"[,;\n]+", str(phone))) if len(n) == 10)
    if not key or not nums:
        return False, "FAST2SMS_KEY (.env) or 10-digit number missing"
    try:
        r = requests.post("https://www.fast2sms.com/dev/bulkV2", headers={"authorization": key},
                          json={"route": "q", "message": text[:300], "numbers": nums, "flash": 0}, timeout=30)
        j = r.json()
        return bool(j.get("return")), str(j.get("message") or j)[:200]
    except Exception as e:
        return False, str(e)

def sms_text(d=None, now=None):
    """Keep the SMS short (each 160 chars is billed as a separate SMS), no emoji."""
    now = now or datetime.now()
    d = copy.deepcopy(d or load_data())
    plan_refresh(d, now)
    p = d["profile"]
    tasks = [t for t in d["plan"]["tasks"] if t["status"] != "missed"][:4]
    head = f"StudyBot {p.get('name') or ''}".strip()
    dl = days_to_exam(p, now)
    if dl is not None and dl >= 0:
        head += f" ({dl} days left)"
    body = "; ".join(f"{fmt(t['start'])} {t['subject']}-{t['topic']}" for t in tasks) or "no plan yet, add a syllabus"
    return re.sub(r"[^\x00-\x7F]+", "", f"{head}: {body}").strip()[:300]

def detect_chat_id(token=None):
    token = token or os.getenv("TELEGRAM_TOKEN")
    if not token:
        return None, "TELEGRAM_TOKEN not found in .env"
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    except Exception as e:
        return None, str(e)
    if r.status_code == 409:
        return None, "409 conflict: stop bot.py and try again"
    for u in reversed(r.json().get("result", [])):
        m = u.get("message") or u.get("edited_message")
        if m:
            return str(m["chat"]["id"]), "OK"
    return None, "First send /start or any message to your bot on Telegram"

def daily_message(d=None, now=None):
    now = now or datetime.now()
    d = copy.deepcopy(d or load_data())
    plan_refresh(d, now)
    p = d["profile"]
    tasks = [t for t in d["plan"]["tasks"] if t["status"] != "missed"]
    L = [f"🌅 Hello {p.get('name') or 'Student'}! Today's StudyBot plan", "",
         f"⏱ Study: {p['hours']}h | Sessions: {len(tasks)}"]
    dl = days_to_exam(p, now)
    if dl is not None and dl >= 0:
        L.append(f"🎯 {exam_label(p)}: {dl} days left")
    L.append("\n📋 Plan:" if tasks else "\n📋 Plan: add a syllabus or no free slot found")
    L += [f"• {fmt(t['start'])}-{fmt(t['end'])} {t['subject']} - {t['topic']}" for t in tasks]
    weak = sorted([(r["m"], k.replace("::", " - ")) for k, r in d["mastery"].items() if r.get("n")])[:3]
    if weak:
        L.append("\n⚠️ Weak topics: " + ", ".join(f"{k} ({m * 100:.0f}%)" for m, k in weak))
    due = []
    for it in d["tracker"]:
        try:
            dd = (datetime.strptime(it["due"], F).date() - now.date()).days
        except Exception:
            continue
        if it["status"] != "Done" and dd <= 7:
            due.append(f"• {it['kind']}: {it['title']} ({it.get('subject', '')}) - {dd} days")
    if due:
        L += ["\n📝 Deadlines:"] + due
    g = d["goals"]
    L.append(f"\n🎯 Goals: {g['focus_min']} min focus + {g['quiz_q']} quiz questions")
    L.append(f"🔥 Streak: {streak(d, now)} days")
    y = (now - timedelta(1)).strftime(F)
    qy = [x for x in d["quiz_log"] if x["date"] == y]
    L.append(f"📊 Yesterday: {focus_by_day(d).get(y, 0)} min focus, quiz {sum(x['correct'] for x in qy)}/{sum(x['total'] for x in qy)}")
    return "\n".join(L)

# ====================== MAIN (UI - keep only pure logic above this line) ======================
frag = st.fragment if hasattr(st, "fragment") else (lambda **kw: (lambda f: f))
PAGES = ["Signup", "Profile", "Syllabus & Material", "Quiz", "Today's Plan", "Focus Mode",
         "Daily Goals", "Progress", "Doubt", "Reminders", "Tests & Assignments"]

def tm(s):
    return datetime.strptime(s, "%H:%M").time()

def page_signup(d):
    st.subheader("1. Signup / Login")
    if st.session_state.auth:
        st.success(f"Logged in: {st.session_state.auth}")
        if st.button("Logout"):
            st.session_state.auth = None
            st.rerun()
        return
    t1, t2 = st.tabs(["Signup", "Login"])
    with t1:
        u, pw = st.text_input("Username", key="su"), st.text_input("Password", type="password", key="sp")
        cid = st.text_input("Telegram Chat ID (reminders will come here)", key="sc")
        st.caption("First press Start on the bot in Telegram, then get your ID from @userinfobot. If you leave it empty, you can add it later on the Reminders page.")
        mob = st.text_input("Mobile number (for SMS reminders, optional)", key="sm")
        if st.button("Create account"):
            users, u = load_users(), u.strip()
            if not u or len(pw) < 4:
                st.error("Enter a username and a password of at least 4 characters")
            elif u in users or u == "demo":
                st.error("This username already exists")
            else:
                s_, h = hash_pw(pw)
                users[u] = {"salt": s_, "hash": h}
                save_users(users)
                nd = default_data()
                nd["_user"] = u
                nd["telegram"].update({"chat_id": cid.strip(), "on": bool(cid.strip())})
                nd["sms"].update({"phone": mob.strip(), "on": bool(mob.strip())})
                save_data(nd)
                if cid.strip():
                    ok, r = send_telegram(f"✅ Your StudyBot account is ready, {u}! Reminders will arrive in this chat.",
                                          chat_id=cid.strip())
                    st.session_state.flash = (ok, "Welcome message sent on Telegram ✅" if ok
                                              else f"Telegram message failed: {r}")
                st.session_state.auth, st.session_state.page = u, 2
                st.rerun()
    with t2:
        u, pw = st.text_input("Username", key="lu"), st.text_input("Password", type="password", key="lp")
        if st.button("Login"):
            rec = load_users().get(u.strip())
            if rec and hash_pw(pw, rec["salt"])[1] == rec["hash"]:
                st.session_state.auth, st.session_state.page = u.strip(), 5
                st.rerun()
            else:
                st.error("Wrong username or password")
    if st.button("Skip (demo mode)"):
        st.session_state.auth, st.session_state.page = "demo", 2
        st.rerun()

def idx(lst, v):
    return lst.index(v) if v in lst else 0

def page_profile(d):
    p = d["profile"]
    st.subheader("2. Profile")
    cat = st.selectbox("Exam category", CATEGORIES, index=idx(CATEGORIES, p.get("category")), key="pcat")
    with st.form("prof"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", p["name"])
        langs = ["Hinglish", "Hindi", "English"]
        lang = c2.selectbox("Language", langs, index=idx(langs, p["language"]))
        ex = {}
        if cat == "Engineering (College Sem)":
            ex["branch"] = c1.selectbox("Branch", BRANCHES, index=idx(BRANCHES, p.get("branch")))
            ex["semester"] = int(c2.number_input("Semester", 1, 8, int(p.get("semester", 3))))
        elif cat == "Class 6-9 School":
            ex["cls"] = int(c1.number_input("Class", 6, 9, int(p.get("cls", 9))))
            ex["board"] = c2.selectbox("Board", BOARDS, index=idx(BOARDS, p.get("board")))
        elif cat == "Class 10 Board":
            ex["board"] = c1.selectbox("Board", BOARDS, index=idx(BOARDS, p.get("board")))
        elif cat == "Class 12 Board":
            ex["board"] = c1.selectbox("Board", BOARDS, index=idx(BOARDS, p.get("board")))
            ex["stream"] = c2.selectbox("Stream", STREAMS, index=idx(STREAMS, p.get("stream")))
        elif cat == "Competitive Exam":
            cur = p.get("exam", "")
            sel = c1.selectbox("Exam", COMP_EXAMS, index=idx(COMP_EXAMS, cur) if cur in COMP_EXAMS else len(COMP_EXAMS) - 1)
            other = c2.text_input("Exam name (if Other)", cur if cur not in COMP_EXAMS else "")
            ex["exam"] = other.strip() if sel == "Other" and other.strip() else sel
        else:
            ex["exam"] = c1.text_input("Exam name", p.get("exam", ""))
        try:
            ed = datetime.strptime(p["exam_date"], F).date()
        except Exception:
            ed = date.today() + timedelta(days=30)
        exam_date = c2.date_input("Exam date", ed)
        hours = st.slider("Daily study hours", 0.5, 10.0, float(p["hours"]), 0.5)
        weak = st.text_input("Weak subjects (comma separated)", ", ".join(p["weak"]))
        st.markdown("**Routine**")
        wake = c1.time_input("Wake up", tm(p["wake"]))
        sleep = c2.time_input("Sleep", tm(p["sleep"]))
        school = st.text_input("School/College/Coaching time (HH:MM-HH:MM)", p["school"])
        meals = st.text_input("Meals (HH:MM-HH:MM, comma separated)", p["meals"])
        fixed = st.text_area("Fixed activities (one per line: 17:00-18:00 Gym)", p["fixed"], height=80)
        if st.form_submit_button("Save"):
            p.update({"name": name, "category": cat, "language": lang, **ex,
                      "exam_date": exam_date.strftime(F), "hours": hours,
                      "weak": [w.strip() for w in weak.split(",") if w.strip()],
                      "wake": wake.strftime("%H:%M"), "sleep": sleep.strftime("%H:%M"),
                      "school": school, "meals": meals, "fixed": fixed})
            plan_refresh(d, force=True)
            save_data(d)
            st.success(f"Saved ✅ {exam_label(p)}")

def page_syllabus(d):
    st.subheader("3. Syllabus & Material")
    p = d["profile"]
    if "syl_text" not in st.session_state:
        st.session_state.syl_text = syllabus_text(d)
    with st.expander("🤖 Draft syllabus with AI"):
        subs = st.text_input("Subjects (comma separated)", value=preset_subjects(p))
        if st.button("Create draft") and subs.strip():
            try:
                with st.spinner("Gemini is thinking..."):
                    st.session_state.syl_text = gemini(
                        f"Official syllabus of the subjects {subs} for {exam_label(p)}. "
                        "Use only this format, one line per subject: 'Subject: topic1, topic2, ...' "
                        "(8-12 chapters/topics). No bullets, numbering or extra text.", 0.3).strip()
                st.rerun()
            except Exception as e:
                st.error(str(e))
    st.text_area('Syllabus (format "Subject: topic1, topic2")', key="syl_text", height=220)
    if st.button("💾 Save syllabus"):
        d["syllabus"] = parse_syllabus(st.session_state.syl_text)
        plan_refresh(d, force=True)
        save_data(d)
        st.success(f"{len(d['syllabus'])} subjects, {len(topic_list(d))} topics saved")
    st.markdown("**📄 Notes (PDF/TXT)**")
    files = st.file_uploader("Notes upload", type=["pdf", "txt"], accept_multiple_files=True)
    if files and st.button("Add notes"):
        for f in files:
            try:
                if f.name.lower().endswith(".pdf"):
                    from pypdf import PdfReader
                    text = "\n".join((pg.extract_text() or "") for pg in PdfReader(f).pages)
                else:
                    text = f.read().decode("utf-8", "ignore")
                d["chunks"] = [c for c in d["chunks"] if c["src"] != f.name] + make_chunks(text, f.name)
            except Exception as e:
                st.error(f"{f.name}: {e}")
        save_data(d)
        st.success("Notes added")
    st.caption(f"Total chunks: {len(d['chunks'])} | files: {len({c['src'] for c in d['chunks']})}")
    if d["chunks"] and st.button("🗑 Remove all notes"):
        d["chunks"] = []
        save_data(d)
        st.rerun()

def page_quiz(d):
    st.subheader("4. Quiz")
    topics = topic_list(d)
    if not topics:
        st.warning("Add a syllabus first (page 3)")
        return
    q = st.session_state.get("quiz")
    if q and not q["done"]:
        st.caption(f"{q['subject']} - {q['topic']}")
        with st.form("quizform"):
            ans = []
            for i, it in enumerate(q["qs"]):
                st.markdown(f"**Q{i + 1}. [{it['type']}]** {it['q']}")
                k = f"a{q['id']}_{i}"
                if it["type"] == "mcq":
                    ans.append(st.radio("Option", it["options"], index=None, key=k, label_visibility="collapsed"))
                elif it["type"] == "theory":
                    ans.append(st.text_area("Answer", key=k, height=100))
                else:
                    ans.append(st.text_input("Answer", key=k))
            sub = st.form_submit_button("Submit quiz")
        if sub:
            with st.spinner("Checking..."):
                q["res"] = [grade_item(it, a) for it, a in zip(q["qs"], ans)]
            ok = sum(1 for r in q["res"] if r[0])
            record_quiz(d, q["subject"], q["topic"], ok, len(q["qs"]), "/".join(sorted({i["type"] for i in q["qs"]})))
            plan_refresh(d, force=True)
            save_data(d)
            q["done"] = True
            st.rerun()
        return
    if q and q["done"]:
        ok = sum(1 for r in q["res"] if r[0])
        st.success(f"Score: {ok}/{len(q['qs'])}  |  {q['subject']} - {q['topic']}")
        for i, (it, (good, note)) in enumerate(zip(q["qs"], q["res"])):
            with st.expander(f"{'✅' if good else '❌'} Q{i + 1}: {it['q'][:60]}"):
                st.markdown(it["q"])
                if it["type"] == "mcq":
                    st.write("Correct:", it["options"][it["answer"]])
                if note:
                    st.write(note)
                st.write(it.get("explain", ""))
        if st.button("➕ New quiz"):
            st.session_state.quiz = None
            st.rerun()
        return
    mode = st.radio("Mode", ["Diagnostic", "Topic practice"], horizontal=True)
    if mode == "Diagnostic":
        s, t = sorted(topics, key=lambda x: (d["mastery"].get(f"{x[0]}::{x[1]}", {}).get("n", 0) > 0,
                                              -priority(d, x[0], x[1])))[0]
        st.info(f"This time: **{s} - {t}** (untested/weak topics first)")
    else:
        s = st.selectbox("Subject", list(d["syllabus"]))
        t = st.selectbox("Topic", d["syllabus"][s])
    types = st.multiselect("Question types", list(QTYPES), default=default_qtypes(d["profile"]))
    c1, c2 = st.columns(2)
    n = c1.slider("Questions", 3, 8, 5)
    level = c2.selectbox("Level", ["Easy", "Medium", "Hard"], index=1)
    if st.button("🎯 Create quiz", type="primary") and types:
        try:
            with st.spinner("Gemini is creating questions..."):
                qs = gen_questions(d, s, t, types, n, level)
            st.session_state.quiz = {"id": secrets.token_hex(2), "subject": s, "topic": t, "qs": qs, "done": False}
            st.rerun()
        except Exception as e:
            st.error(str(e))

@frag(run_every=60)
def plan_view():
    d = load_data()
    if plan_refresh(d):
        save_data(d)
    tasks, p = d["plan"]["tasks"], d["profile"]
    done_min = sum(t["end"] - t["start"] for t in tasks if t["status"] == "done")
    dl = days_to_exam(p)
    st.caption(f"Cap: {p['hours']}h | Done: {done_min} min | 50 min block + 10 min break"
               + (f" | {dl} days to exam" if dl is not None and dl >= 0 else ""))
    if not tasks:
        st.info("No slots left for today (check your routine/hours).")
    icon = {"pending": "⏳", "done": "✅", "missed": "❌", "skipped": "⏭"}
    for t in tasks:
        c1, c2, c3 = st.columns([6, 1, 1])
        c1.markdown(f"{icon[t['status']]} **{fmt(t['start'])}-{fmt(t['end'])}** {t['subject']} - {t['topic']}")
        if t["status"] == "pending":
            if c2.button("✅", key="d" + t["id"]):
                set_task_status(d, t["id"], "done"); save_data(d); st.rerun()
            if c3.button("⏭", key="s" + t["id"]):
                set_task_status(d, t["id"], "skipped"); plan_refresh(d, force=True); save_data(d); st.rerun()

def page_plan(d):
    st.subheader("5. Today's Plan")
    if not topic_list(d):
        st.warning("Add a syllabus first (page 3)")
        return
    if st.button("🔄 Regenerate plan"):
        plan_refresh(d, force=True); save_data(d); st.rerun()
    plan_view()

def finish_focus(minutes, task_id=None):
    d = load_data()
    d["focus"].append({"date": today_str(), "min": int(minutes), "task": task_id})
    if task_id:
        set_task_status(d, task_id, "done")
    save_data(d)

@frag(run_every=1)
def focus_timer():
    end = st.session_state.get("focus_end")
    if not end:
        return
    left = int(end - time.time())
    if left <= 0:
        finish_focus(st.session_state.focus_len, st.session_state.get("focus_task"))
        st.session_state.focus_end = None
        st.session_state.focus_msg = f"🎉 {st.session_state.focus_len} min session complete!"
        st.rerun()
        return
    st.markdown(f"<h1 style='text-align:center'>{left // 60:02d}:{left % 60:02d}</h1>", unsafe_allow_html=True)
    st.progress(1 - left / (st.session_state.focus_len * 60))

def focus_bridge(active, end_ts=None, label=""):
    """StudyBot Focus Blocker (Chrome extension) ko session ka haal batata hai.
    Extension na ho to bhi kuch nahi bigadta (sirf ek chhota note dikhta hai)."""
    try:
        import streamlit.components.v1 as components
        msg = json.dumps({"type": "studybot-focus", "active": bool(active),
                          "end": int(end_ts * 1000) if end_ts else 0, "topic": label})
        ok_txt = json.dumps("🔒 Chrome blocker ON: distracting websites band hain" if active
                            else "✅ Chrome blocker connected")
        components.html(f"""<div id="s" style="font:13px sans-serif;color:#64748b"></div>
<script>
const s=document.getElementById('s');let ok=false;
window.addEventListener('message',e=>{{if(e.data&&e.data.type==='studybot-ext-ack'){{ok=true;s.textContent={ok_txt};}}}});
window.parent.postMessage({msg},'*');
setTimeout(()=>{{if(!ok)s.textContent='ℹ️ Chrome Focus Blocker extension nahi mila (optional). Websites block karne ke liye install karo.';}},1500);
</script>""", height=34)
    except Exception:
        pass


def page_focus(d):
    st.subheader("6. Focus Mode")
    if st.session_state.get("focus_msg"):
        st.success(st.session_state.pop("focus_msg"))
        st.balloons()
    if st.session_state.get("focus_end"):
        _tid = st.session_state.get("focus_task")
        _t = next((x for x in d.get("plan", {}).get("tasks", []) if x["id"] == _tid), None)
        focus_bridge(True, st.session_state.focus_end, f"{_t['subject']} - {_t['topic']}" if _t else "Focus")
        focus_timer()
        if st.button("⏹ Stop"):
            mins = int((time.time() - (st.session_state.focus_end - st.session_state.focus_len * 60)) / 60)
            if mins >= 1:
                finish_focus(mins)
            st.session_state.focus_end = None
            st.rerun()
    else:
        mins = st.radio("Duration (min)", [15, 25, 50, 90], index=1, horizontal=True)
        pend = [t for t in d.get("plan", {}).get("tasks", []) if t["status"] == "pending"]
        opts = {"- none -": None, **{f"{fmt(t['start'])} {t['subject']} - {t['topic']}": t["id"] for t in pend}}
        pick = st.selectbox("Plan task (auto-marked done when finished)", list(opts))
        if st.button("▶ Start", type="primary"):
            st.session_state.update(focus_end=time.time() + mins * 60, focus_len=mins, focus_task=opts[pick])
            st.rerun()
        focus_bridge(False)
    fm, _ = today_stats(d)
    c1, c2 = st.columns(2)
    c1.metric("Today's focus", f"{fm} min")
    c2.metric("🔥 Streak", f"{streak(d)} days")

def page_goals(d):
    st.subheader("7. Daily Goals")
    g = d["goals"]
    c1, c2 = st.columns(2)
    g["focus_min"] = c1.number_input("Focus target (min)", 0, 600, int(g["focus_min"]), 10)
    g["quiz_q"] = c2.number_input("Quiz questions target", 0, 200, int(g["quiz_q"]), 5)
    fm, qq = today_stats(d)
    st.write(f"Focus: {fm}/{g['focus_min']} min")
    st.progress(min(fm / max(g["focus_min"], 1), 1.0))
    st.write(f"Quiz: {qq}/{g['quiz_q']} questions")
    st.progress(min(qq / max(g["quiz_q"], 1), 1.0))
    tasks = d.get("plan", {}).get("tasks", []) if d.get("plan", {}).get("date") == today_str() else []
    if tasks:
        dn = sum(t["status"] == "done" for t in tasks)
        st.write(f"Plan tasks: {dn}/{len(tasks)}")
        st.progress(dn / len(tasks))
    st.markdown("**✅ Custom checklist**")
    new = st.text_input("New goal", key="newgoal")
    if st.button("Add") and new.strip():
        g["custom"].append({"id": secrets.token_hex(3), "t": new.strip(), "done": False, "date": today_str()})
        save_data(d); st.session_state.pop("newgoal", None); st.rerun()
    for it in g["custom"]:
        if it["done"] and it["date"] != today_str():
            continue
        v = st.checkbox(it["t"], it["done"], key="c" + it["id"])
        if v != it["done"]:
            it["done"], it["date"] = v, today_str()
            save_data(d)
    st.metric("🔥 Streak", f"{streak(d)} days")
    save_data(d)

def page_progress(d):
    st.subheader("8. Progress")
    import pandas as pd
    rows = []
    for s, t in topic_list(d):
        r = d["mastery"].get(f"{s}::{t}")
        rows.append({"Subject": s, "Topic": t, "Mastery %": round(r["m"] * 100) if r else None,
                     "Attempts": r["n"] if r else 0,
                     "Accuracy %": round(r["c"] / r["t"] * 100) if r and r["t"] else None,
                     "Priority": round(priority(d, s, t), 2)})
    if not rows:
        st.info("Add a syllabus.")
        return
    st.dataframe(pd.DataFrame(rows).sort_values("Priority", ascending=False), hide_index=True, use_container_width=True)
    if d["quiz_log"]:
        df = pd.DataFrame(d["quiz_log"]).groupby("date")[["correct", "total"]].sum()
        st.markdown("**Accuracy trend (%)**")
        st.line_chart((df["correct"] / df["total"] * 100).rename("Accuracy"))

def page_doubt(d):
    st.subheader("9. Doubt")
    hist = st.session_state.setdefault("chat", [])
    for m in hist:
        st.chat_message(m["role"]).write(m["content"])
    q = st.chat_input("Write your doubt...")
    if q:
        st.chat_message("user").write(q)
        hist.append({"role": "user", "content": q})
        ctx = retrieve(d, q)
        p = d["profile"]
        notes = "\n---\n".join(c["text"] for c in ctx) or "(nothing found in notes)"
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in hist[-7:-1])
        prompt = (f"You are a tutor for a {exam_label(p)} student. Explain in {p['language']} with simple steps and "
                  f"examples. Use the NOTES first; if the answer is not there, say 'not found in notes' and then give a general "
                  f"answer.\nNOTES:\n{notes}\n\nCHAT:\n{convo}\n\nQUESTION: {q}")
        try:
            with st.spinner("..."):
                a = gemini(prompt, 0.3)
        except Exception as e:
            a = f"Error: {e}"
        st.chat_message("assistant").write(a)
        hist.append({"role": "assistant", "content": a})
        if ctx:
            with st.expander("Sources"):
                for c in ctx:
                    st.caption(f"{c['src']}: {c['text'][:150]}...")

def page_reminders(d):
    st.subheader("10. Reminders (Telegram)")
    tg = d["telegram"]
    st.caption("Token: " + ("✅ found" if os.getenv("TELEGRAM_TOKEN") else "❌ Add TELEGRAM_TOKEN to .env"))
    tg["chat_id"] = st.text_input("Chat ID (you can add friends' IDs too, comma separated: 7071197028, 1234567890)", tg["chat_id"])
    st.caption("Each friend must press Start on your bot first. Their ID can be found via @userinfobot.")
    if st.button("🔍 Auto-detect Chat ID (adds the latest message sender)"):
        cid, msg = detect_chat_id()
        if cid:
            ids = [x for x in re.split(r"[,\s;]+", tg["chat_id"]) if x]
            if cid not in ids:
                ids.append(cid)
            tg["chat_id"] = ", ".join(ids); save_data(d); st.rerun()
        else:
            st.error(msg)
    tg["time"] = st.time_input("Daily time", tm(tg["time"])).strftime("%H:%M")
    tg["on"] = st.toggle("Reminder ON", tg["on"])
    if st.button("💾 Save"):
        save_data(d); st.success("Saved")
    c1, c2 = st.columns(2)
    if c1.button("📨 Test message"):
        ok, r = send_telegram("✅ StudyBot test message", d=d)
        if ok:
            st.success("Sent")
        else:
            st.error(r)
    if c2.button("📋 Send today's plan now"):
        ok, r = send_telegram(daily_message(d), d=d)
        if ok:
            st.success("Sent")
        else:
            st.error(r)
    st.markdown("---")
    st.markdown("**📱 WhatsApp (on your own number, free)**")
    st.caption("Setup: open callmebot.com/blog/free-api-whatsapp-messages, save the bot number shown there in your contacts, "
               "and send it 'I allow callmebot to send me messages' on WhatsApp. Enter the API key you get here. "
               "This is an unofficial free service, only for your own number.")
    w = d["whatsapp"]
    w["phone"] = st.text_input("WhatsApp number (with country code, e.g. 919876543210)", w["phone"])
    w["apikey"] = st.text_input("CallMeBot API key", w["apikey"], type="password")
    w["on"] = st.toggle("WhatsApp reminder ON", w["on"])
    if st.button("💾 WhatsApp save"):
        save_data(d); st.success("Saved")
    c3, c4 = st.columns(2)
    if c3.button("📨 WhatsApp test"):
        ok, r = send_whatsapp("✅ StudyBot test message", d)
        if ok:
            st.success("Sent")
        else:
            st.error(r)
    if c4.button("📋 Send plan on WhatsApp"):
        ok, r = send_whatsapp(daily_message(d), d)
        if ok:
            st.success("Sent")
        else:
            st.error(r)
    st.markdown("---")
    st.markdown("**💬 SMS (Fast2SMS)**")
    st.caption("Add FAST2SMS_KEY=... to .env. " + ("✅ key found" if os.getenv("FAST2SMS_KEY") else "❌ key not found")
               + " | Each SMS uses credit, so keep it ON only when needed.")
    sm = d["sms"]
    sm["phone"] = st.text_input("SMS number (10 digits, comma separated for several)", sm["phone"])
    sm["on"] = st.toggle("SMS reminder ON", sm["on"])
    if st.button("💾 SMS save"):
        save_data(d); st.success("Saved")
    c5, c6 = st.columns(2)
    if c5.button("📨 SMS test"):
        ok, r = send_sms("StudyBot test SMS", d=d)
        if ok:
            st.success("SMS sent")
        else:
            st.error(r)
    if c6.button("📋 Send plan by SMS"):
        ok, r = send_sms(sms_text(d), d=d)
        if ok:
            st.success("SMS sent")
        else:
            st.error(r)
    st.caption("For daily auto-send: python notify.py --loop (or Task Scheduler)")

def page_tracker(d):
    st.subheader("11. Tests & Assignments")
    with st.form("trk", clear_on_submit=True):
        c1, c2 = st.columns(2)
        kind, subj = c1.selectbox("Type", KINDS), c2.text_input("Subject")
        title = c1.text_input("Title (e.g. Unit Test 2 / Mock 5 / Lab 4)")
        due = c2.date_input("Deadline / date", date.today() + timedelta(days=7))
        if st.form_submit_button("➕ Add") and title.strip():
            d["tracker"].append({"id": secrets.token_hex(3), "kind": kind, "subject": subj.strip(),
                                 "title": title.strip(), "due": due.strftime(F), "status": "Pending"})
            plan_refresh(d, force=True); save_data(d); st.rerun()
    for it in sorted(d["tracker"], key=lambda x: (x["status"] == "Done", x["due"])):
        days = (datetime.strptime(it["due"], F).date() - date.today()).days
        c1, c2, c3 = st.columns([5, 3, 1])
        tag = "🔴 overdue" if days < 0 and it["status"] != "Done" else f"{days} days"
        c1.markdown(f"**{it['kind']}**: {it['title']}  \n{it.get('subject', '')} | {it['due']} ({tag})")
        new = c2.selectbox("S", STAT, STAT.index(it["status"]), key="s_" + it["id"], label_visibility="collapsed")
        if new != it["status"]:
            it["status"] = new; save_data(d); st.rerun()
        if c3.button("🗑", key="x_" + it["id"]):
            d["tracker"].remove(it); save_data(d); st.rerun()

import html as _html

ICONS = ["👤", "🧾", "📚", "🧠", "📅", "⏱", "🎯", "📈", "💬", "🔔", "📝"]
CSS = """
<style>
:root{--navy:#102b5c;--blue:#2563eb;--sky:#eaf3ff;--bg:#f5f8ff;--ink:#17243b;--muted:#64748b;--line:#dce6f5;
      --green:#15803d;--orange:#b45309;--red:#b91c1c}
html,body,.stApp,[class*="css"]{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
.stApp{background:var(--bg);color:var(--ink)}
.block-container{padding-top:1.2rem;max-width:920px}
h1,h2,h3,h4{color:var(--navy)}
.hero{background:linear-gradient(135deg,var(--navy) 0%,var(--blue) 100%);padding:18px 22px;border-radius:18px;
      color:#fff;margin-bottom:16px;box-shadow:0 8px 22px rgba(16,43,92,.22)}
.hero h1{margin:0;font-size:1.55rem;color:#fff;padding:0}
.hero p{margin:5px 0 0;opacity:.92;font-size:.95rem}
div.stButton>button,div.stFormSubmitButton>button{border-radius:12px;font-weight:750;padding:.55rem .95rem}
[data-testid="stBaseButton-primary"],button[kind="primary"],[data-testid="stBaseButton-primaryFormSubmit"]{
      background:var(--blue);color:#fff;border:0}
[data-testid="stBaseButton-secondary"],button[kind="secondary"],[data-testid="stBaseButton-secondaryFormSubmit"]{
      background:#fff;color:var(--navy);border:1px solid var(--line)}
[data-testid="stBaseButton-secondary"]:hover,button[kind="secondary"]:hover{background:var(--sky);border-color:var(--blue)}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line)}
[data-testid="stSidebar"] div.stButton>button{justify-content:flex-start;text-align:left}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 14px;
      box-shadow:0 2px 8px rgba(16,43,92,.06)}
[data-testid="stMetricLabel"]{color:var(--muted)}
[data-testid="stForm"],[data-testid="stExpander"]{background:#fff;border:1px solid var(--line);border-radius:16px}
input,textarea,[data-baseweb="select"]>div{border-radius:10px!important}
.stProgress>div>div>div>div{background:var(--blue)}
hr{border-color:var(--line)}
</style>
"""

st.set_page_config(page_title="StudyBot AI", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)
D = load_data()
st.session_state.setdefault("auth", None)
st.session_state.setdefault("page", 1)
if not st.session_state.auth:
    st.session_state.page = 1

with st.sidebar:
    st.markdown("### 🎓 StudyBot AI")
    if st.session_state.auth:
        for i, name in enumerate(PAGES):
            if st.button(f"{ICONS[i]} {i + 1}. {name}", key=f"nav{i}", use_container_width=True,
                         type="primary" if st.session_state.page == i + 1 else "secondary"):
                st.session_state.page = i + 1
                st.rerun()
        st.divider()
        st.caption(f"🔥 Streak: {streak(D)} days | ⏱ Today: {today_stats(D)[0]} min")
    else:
        st.info("Please sign up / log in or use Skip (demo) first.")

_p = D["profile"]
_dl = days_to_exam(_p)
_sub = _html.escape(exam_label(_p)) + (f" • {_dl} days left" if _dl is not None and _dl >= 0 else "")
_hi = f"Hello {_html.escape(_p['name'])}! " if _p.get("name") else ""
st.markdown(f"<div class='hero'><h1>🎓 {_hi}StudyBot AI</h1><p>{_sub}</p></div>", unsafe_allow_html=True)

_fl = st.session_state.pop("flash", None)
if _fl:
    (st.success if _fl[0] else st.warning)(_fl[1])

{1: page_signup, 2: page_profile, 3: page_syllabus, 4: page_quiz, 5: page_plan, 6: page_focus,
 7: page_goals, 8: page_progress, 9: page_doubt, 10: page_reminders, 11: page_tracker}[st.session_state.page](D)
