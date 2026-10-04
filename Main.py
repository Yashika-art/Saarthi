import base64, json, os, re, time
from collections import defaultdict
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import Anthropic

load_dotenv()
client = Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
MAX_BYTES = 8 * 1024 * 1024
LIMIT, WINDOW = 25, 3600  # requests per IP per hour (protects your credits)
HITS = defaultdict(list)

app = FastAPI(title="Saarthi")

BASE = """You are Saarthi, a kind helper for people with low literacy or poor eyesight.
Write ALL text in {language}, in very simple everyday words and short sentences, like speaking to an elder in the family. No markdown, no emojis.
{task}
If the photo is unreadable, say so and ask for a clearer photo in better light."""

JSON_RULE = """Reply with ONLY one JSON object, no code fences:
{"title": "2-4 word name of the item", "risk": "safe|caution|danger", "spoken": "the explanation, max 100 words", "facts": [{"label": "...", "value": "..."}], "due_date": "YYYY-MM-DD or null"}
facts: at most 4 key items (amount, date, dose, who it is from), labels and values in {language}.
risk: danger = likely scam or serious hazard; caution = needs attention soon or looks unusual; safe = routine."""

TASKS = {
    "auto": "Say what this is, the most important facts (amounts, dates, names), and what the person should do next. Warn clearly if anything looks risky.",
    "medicine": "This is a medicine. Give its name, usual use, how and when it is taken as printed, expiry date and printed warnings. Never invent a dose. End by saying to confirm with a doctor or pharmacist.",
    "bill": "This is a bill. Say who it is from, the amount, the last date, and what happens if unpaid. Mention strange or extra charges.",
    "notice": "This is an official letter or notice. Explain what it asks, any deadline, and where to go. Say if it is urgent.",
    "scam": "Check if this looks like a scam or fraud. Say clearly if it is safe, suspicious or a likely scam, give the main reasons, and what NOT to do (never share OTP, PIN or send money).",
}

def system(language, mode, structured=True):
    s = BASE.replace("{language}", language).replace("{task}", TASKS.get(mode, TASKS["auto"]))
    return s + ("\n" + JSON_RULE.replace("{language}", language) if structured else "\nReply in plain text, max 80 words.")

def text_of(resp):
    return "".join(b.text for b in resp.content if b.type == "text").strip()

def parse(raw):
    try:
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip())
        d["spoken"] = str(d["spoken"])
    except Exception:
        d = {"spoken": raw}
    d["facts"] = [f for f in d.get("facts", []) if isinstance(f, dict) and "label" in f and "value" in f][:4]
    d["risk"] = d.get("risk") if d.get("risk") in ("safe", "caution", "danger") else None
    due = d.get("due_date")
    d["due_date"] = due if isinstance(due, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) else None
    d["title"] = d.get("title") or None
    return d

def limit(req: Request):
    ip = (req.headers.get("x-forwarded-for") or req.client.host).split(",")[0].strip()
    now = time.time()
    HITS[ip] = [t for t in HITS[ip] if now - t < WINDOW]
    if len(HITS[ip]) >= LIMIT:
        raise HTTPException(429, "Too many requests. Please try again in a while.")
    HITS[ip].append(now)

@app.post("/api/explain")
async def explain(req: Request, image: Optional[UploadFile] = File(None), text: str = Form(""),
                  language: str = Form("Hindi"), mode: str = Form("auto")):
    limit(req)
    content = []
    if image is not None:
        data = await image.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Image too large")
        media = image.content_type if image.content_type in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
        content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                    "data": base64.b64encode(data).decode()}})
    if text.strip():
        content.append({"type": "text", "text": "Please explain this message to me:\n" + text.strip()[:4000]})
    elif not content:
        raise HTTPException(400, "Send a photo or some text")
    else:
        content.append({"type": "text", "text": "Please explain this to me."})
    try:
        resp = client.messages.create(model=MODEL, max_tokens=800, system=system(language, mode),
                                      messages=[{"role": "user", "content": content}])
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")
    return parse(text_of(resp))

class Ask(BaseModel):
    question: str
    context: str
    language: str = "Hindi"
    mode: str = "auto"

@app.post("/api/ask")
async def ask(req: Request, body: Ask):
    limit(req)
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=500, system=system(body.language, body.mode, structured=False),
            messages=[{"role": "user", "content": "I showed you a document. Explain it."},
                      {"role": "assistant", "content": body.context},
                      {"role": "user", "content": body.question}])
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")
    return {"text": text_of(resp)}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("static/index.html")
