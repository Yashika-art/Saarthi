import base64, os
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import Anthropic

load_dotenv()
client = Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
MAX_BYTES = 8 * 1024 * 1024

app = FastAPI(title="Saarthi")

BASE = """You are Saarthi, a kind helper for people who have low literacy or poor eyesight.
Reply ONLY in {language}, in very simple everyday words and short sentences, like speaking to an elder in the family.
No markdown, no bullet symbols, no emojis. Maximum 110 words.
{task}
If the image is blurry or unreadable, say so and ask them to take the photo again in better light."""

TASKS = {
    "auto": "First say what this is (bill, medicine, notice, form, sign or something else). Then the most important facts: amounts, dates, names. Then what the person should do next. Warn clearly if anything looks risky.",
    "medicine": "This is a medicine. Say its name, what it is usually used for, how and when it is normally taken as printed on it, the expiry date, and any warning printed. Never invent a dose. End by telling them to confirm with a doctor or pharmacist.",
    "bill": "This is a bill. Say who it is from, the amount to pay, the last date, and what happens if they do not pay. Mention any strange or extra charges.",
    "notice": "This is an official letter or notice. Explain what it wants from the person, any deadline, and where to go. Tell them if it is something they must act on urgently.",
    "scam": "Check whether this message, letter or notice looks like a scam or fraud. Say clearly 'safe', 'suspicious' or 'likely scam', give the main reasons, and tell them what NOT to do (do not share OTP, PIN or send money).",
}

def system(language: str, mode: str) -> str:
    return BASE.format(language=language, task=TASKS.get(mode, TASKS["auto"]))

def text_of(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text").strip()

@app.post("/api/explain")
async def explain(image: UploadFile = File(...), language: str = Form("Hindi"), mode: str = Form("auto")):
    data = await image.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image too large")
    media = image.content_type if image.content_type in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=700, system=system(language, mode),
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media,
                                              "data": base64.b64encode(data).decode()}},
                {"type": "text", "text": "Please explain this to me."}]}],
        )
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")
    return {"text": text_of(resp)}

class Ask(BaseModel):
    question: str
    context: str
    language: str = "Hindi"
    mode: str = "auto"

@app.post("/api/ask")
async def ask(body: Ask):
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=500, system=system(body.language, body.mode),
            messages=[
                {"role": "user", "content": "I showed you a document. Explain it."},
                {"role": "assistant", "content": body.context},
                {"role": "user", "content": body.question}],
        )
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")
    return {"text": text_of(resp)}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("static/index.html")
