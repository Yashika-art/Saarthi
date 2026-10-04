# Saarthi: AI visual assistant in Indian languages

Point your phone at a bill, medicine strip or official letter. Saarthi explains it in simple spoken
Hindi, Bengali, Tamil and more, flags dates, warnings and scams, and answers follow-up questions by voice.

Built for HackNowa Global Hackathon 2026 (Inclusive Technology).

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
uvicorn main:app --reload
```
Open http://localhost:8000. Camera and microphone need HTTPS on phones (use ngrok or deploy to Render).

## Stack
FastAPI, Claude vision API, browser Web Speech API (speech-to-text and text-to-speech).
